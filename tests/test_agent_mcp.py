import asyncio
import socket
import subprocess
import sys
import time

import pytest
from contextlib import asynccontextmanager
from types import SimpleNamespace

from workshop.agent.mcp_client import MCPConnection, MCPToolAdapter


def test_stdio_session_initializes_lists_calls_and_closes(monkeypatch):
    events = []

    @asynccontextmanager
    async def transport(params):
        events.append(("start", params.command, params.args))
        yield ("read", "write")
        events.append(("transport_closed",))

    class Session:
        def __init__(self, read, write):
            assert (read, write) == ("read", "write")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            events.append(("session_closed",))

        async def initialize(self):
            events.append(("initialize",))

        async def list_tools(self, **kwargs):
            return SimpleNamespace(tools=["tool"], next_cursor=None)

        async def call_tool(self, name, arguments):
            return (name, arguments)

        async def list_resources(self, **kwargs):
            return SimpleNamespace(resources=["resource"], next_cursor=None)

        async def read_resource(self, uri):
            return uri

        async def list_prompts(self, **kwargs):
            return SimpleNamespace(prompts=["prompt"], next_cursor=None)

        async def get_prompt(self, name, arguments):
            return name, arguments

    monkeypatch.setattr("workshop.agent.mcp_client.stdio_client", transport)
    monkeypatch.setattr("workshop.agent.mcp_client.ClientSession", Session)

    async def run():
        async with MCPConnection(
            {"transport": "stdio", "command": "server", "args": ["x"]}
        ) as client:
            assert await client.list_tools() == ["tool"]
            assert await client.call_tool("echo", {"x": 1}) == (
                "echo",
                {"x": 1},
            )
            assert await client.list_resources() == ["resource"]
            assert await client.read_resource("file:///x") == "file:///x"
            assert await client.list_prompts() == ["prompt"]
            assert await client.get_prompt("example", {"a": "b"}) == (
                "example",
                {"a": "b"},
            )

    asyncio.run(run())
    assert events == [
        ("start", "server", ["x"]),
        ("initialize",),
        ("session_closed",),
        ("transport_closed",),
    ]


def test_real_stdio_server_round_trip(tmp_path):
    server = tmp_path / "server.py"
    server.write_text("""\
from mcp.server.mcpserver import MCPServer
server = MCPServer("test")
@server.tool()
def greet(name: str) -> str:
    return "hello " + name
@server.tool()
def large() -> str:
    return "x" * 100000
@server.resource("test://sample")
def sample() -> str:
    return "resource content"
@server.prompt()
def greeting(name: str) -> str:
    return "greet " + name
if __name__ == "__main__":
    server.run(transport="stdio")
""")

    async def run():
        async with MCPConnection(
            {
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(server)],
            }
        ) as client:
            assert "greet" in [tool.name for tool in await client.list_tools()]
            result = await client.call_tool("greet", {"name": "Ada"})
            assert not result.is_error
            assert "hello Ada" in str(result.content)
            assert "test://sample" in [
                str(resource.uri) for resource in await client.list_resources()
            ]
            resource = await client.read_resource("test://sample")
            assert "resource content" in str(resource.contents)
            assert "greeting" in [
                prompt.name for prompt in await client.list_prompts()
            ]
            prompt = await client.get_prompt("greeting", {"name": "Ada"})
            assert "greet Ada" in str(prompt.messages)
            adapter = MCPToolAdapter("demo", client)
            tools = await adapter.discover()
            names = {tool.name for tool in tools}
            assert {
                "mcp__demo__greet",
                "mcp__demo__list_resources",
                "mcp__demo__read_resource",
                "mcp__demo__list_prompts",
                "mcp__demo__get_prompt",
            } <= names
            result = await adapter.call("mcp__demo__greet", {"name": "Ada"})
            assert "hello Ada" in result
            result = await adapter.call("mcp__demo__large", {})
            assert len(result) <= 50000
            assert result.endswith("\n[output truncated]")
            assert "resource content" in await adapter.call(
                "mcp__demo__read_resource", {"uri": "test://sample"}
            )
            assert "greet Ada" in await adapter.call(
                "mcp__demo__get_prompt",
                {"name": "greeting", "arguments": {"name": "Ada"}},
            )

    asyncio.run(run())


def test_real_streamable_http_server_round_trip(tmp_path):
    server = tmp_path / "server_http.py"
    server.write_text("""\
import sys
from mcp.server.mcpserver import MCPServer
server = MCPServer("http-test")
@server.tool()
def echo(text: str) -> str:
    return text
if __name__ == "__main__":
    server.run(transport="streamable-http", host="127.0.0.1",
               port=int(sys.argv[1]))
""")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, str(server), str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                with socket.create_connection(
                    ("127.0.0.1", port), timeout=0.2
                ):
                    break
            except OSError:
                if time.monotonic() >= deadline or process.poll() is not None:
                    raise RuntimeError("MCP HTTP server failed to start")
                time.sleep(0.05)

        async def run():
            async with MCPConnection(
                {"transport": "http", "url": f"http://127.0.0.1:{port}/mcp"}
            ) as client:
                assert "echo" in [
                    tool.name for tool in await client.list_tools()
                ]
                result = await client.call_tool("echo", {"text": "hello"})
                assert "hello" in str(result.content)

        asyncio.run(run())
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize("kind", ["tool", "resource", "prompt", "list"])
def test_mcp_adapter_bounds_serialized_results(kind, monkeypatch):
    class Connection:
        async def call_tool(self, name, arguments):
            return {"content": "x" * 100000}

        async def read_resource(self, uri):
            return {"contents": "x" * 100000}

        async def get_prompt(self, name, arguments):
            return {"messages": "x" * 100000}

        async def list_resources(self):
            return [{"text": "x" * 1000} for _ in range(100)]

    async def run():
        adapter = MCPToolAdapter("demo", Connection())
        adapter._remote_tools.add("large")
        names = {
            "tool": ("large", {}),
            "resource": ("read_resource", {"uri": "test://x"}),
            "prompt": ("get_prompt", {"name": "x"}),
            "list": ("list_resources", {}),
        }
        name, args = names[kind]
        result = await adapter.call(adapter.prefix + name, args)
        assert len(result) <= 50000
        assert result.endswith("\n[output truncated]")

    # The adapter must not build a complete JSON string before truncating it.
    monkeypatch.setattr(
        "workshop.agent.mcp_client.json.dumps",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("unbounded serialization")
        ),
    )
    asyncio.run(run())


def test_mcp_adapter_preserves_small_json_and_exact_limit():
    import json

    class Connection:
        async def read_resource(self, uri):
            return {"text": "x" * (50000 - len('{"text": ""}'))}

    async def run():
        adapter = MCPToolAdapter("demo", Connection())
        result = await adapter.call(
            "mcp__demo__read_resource", {"uri": "test://x"}
        )
        assert len(result) == 50000
        assert json.loads(result)["text"].startswith("x")
        assert "[output truncated]" not in result

    asyncio.run(run())


def test_mcp_adapter_rejects_colliding_tool_names():
    class Connection:
        async def list_tools(self):
            return [
                SimpleNamespace(
                    name="read_resource",
                    description="collision",
                    input_schema={},
                )
            ]

    async def run():
        adapter = MCPToolAdapter("demo", Connection())
        with pytest.raises(ValueError, match="conflicting"):
            await adapter.discover()
        with pytest.raises(ValueError, match="does not belong"):
            await adapter.call(
                "mcp__other__read_resource", {"uri": "test://x"}
            )

    asyncio.run(run())


def test_stdio_env_from_resolves_secret_at_connection_time(monkeypatch):
    events = []
    monkeypatch.setenv("MCP_TOKEN_TEST", "secret-value")

    @asynccontextmanager
    async def transport(params):
        events.append(params.env)
        yield ("read", "write")

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

    monkeypatch.setattr("workshop.agent.mcp_client.stdio_client", transport)
    monkeypatch.setattr("workshop.agent.mcp_client.ClientSession", Session)

    async def run():
        async with MCPConnection(
            {
                "transport": "stdio",
                "command": "fake",
                "env": {"MODE": "read"},
                "env_from": {"TOKEN": "MCP_TOKEN_TEST"},
            }
        ):
            pass

    asyncio.run(run())
    assert events == [{"MODE": "read", "TOKEN": "secret-value"}]


def test_http_headers_are_loaded_from_environment(monkeypatch):
    events = []
    monkeypatch.setenv("MCP_AUTH_TEST", "Bearer secret")

    @asynccontextmanager
    async def transport(url, *, http_client):
        events.append(http_client.headers["Authorization"])
        yield ("read", "write")

    class Session:
        def __init__(self, *args):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def initialize(self):
            pass

    monkeypatch.setattr(
        "workshop.agent.mcp_client.streamable_http_client", transport
    )
    monkeypatch.setattr("workshop.agent.mcp_client.ClientSession", Session)

    async def run():
        async with MCPConnection(
            {
                "transport": "http",
                "url": "https://example.test/mcp",
                "headers_env": {"Authorization": "MCP_AUTH_TEST"},
            }
        ):
            pass

    asyncio.run(run())
    assert events == ["Bearer secret"]


def test_http_missing_header_variable_fails(monkeypatch):
    monkeypatch.delenv("MCP_MISSING_TEST", raising=False)

    async def run():
        with pytest.raises(ValueError, match="MCP|environment variable"):
            async with MCPConnection(
                {
                    "transport": "http",
                    "url": "https://example.test",
                    "headers_env": {"Authorization": "MCP_MISSING_TEST"},
                }
            ):
                pass

    asyncio.run(run())


def test_http_initialization_failure_closes_transport(monkeypatch):
    events = []

    @asynccontextmanager
    async def transport(url):
        events.append(url)
        try:
            yield ("read", "write", None)
        finally:
            events.append("closed")

    class Session:
        def __init__(self, read, write):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            events.append("session_closed")

        async def initialize(self):
            raise RuntimeError("init failed")

    monkeypatch.setattr(
        "workshop.agent.mcp_client.streamable_http_client", transport
    )
    monkeypatch.setattr("workshop.agent.mcp_client.ClientSession", Session)

    async def run():
        with pytest.raises(RuntimeError, match="init failed"):
            async with MCPConnection(
                {"transport": "http", "url": "https://example.test/mcp"}
            ):
                pass

    asyncio.run(run())
    assert events == ["https://example.test/mcp", "session_closed", "closed"]
