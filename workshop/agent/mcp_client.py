"""Async MCP connection primitives for the agent's future tool integration."""

import json
import os
import re
from contextlib import AsyncExitStack

import llm
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams
from mcp.shared._httpx_utils import create_mcp_http_client


class MCPConnection:
    """Keep one MCP server session open for discovery and calls.

    Callers must use the connection on the same async task and close it with
    its context manager. Configurations are trusted: stdio launches a process.
    """

    def __init__(self, config):
        self.config = dict(config)
        self._stack = None
        self.session = None

    async def __aenter__(self):
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            transport = self.config.get("transport")
            if transport == "stdio":
                env = dict(self.config.get("env") or {})
                references = self.config.get("env_from", {})
                if not isinstance(references, dict):
                    raise ValueError(
                        "env_from must map names to environment variables"
                    )
                for name, variable in references.items():
                    if (
                        not isinstance(name, str)
                        or not isinstance(variable, str)
                        or not os.environ.get(variable)
                    ):
                        raise ValueError(
                            "Missing or invalid environment variable "
                            f"for {name!r}"
                        )
                    env[name] = os.environ[variable]
                params = StdioServerParameters(
                    command=self.config["command"],
                    args=self.config.get("args", []),
                    env=env or None,
                    cwd=self.config.get("cwd"),
                )
                streams = await stack.enter_async_context(stdio_client(params))
            elif transport == "http":
                header_env = self.config.get("headers_env", {})
                if not isinstance(header_env, dict):
                    raise ValueError(
                        "headers_env must map header names to "
                        "environment variable names"
                    )
                headers = {}
                for header, variable in header_env.items():
                    if (
                        not isinstance(header, str)
                        or not isinstance(variable, str)
                        or not os.environ.get(variable)
                    ):
                        raise ValueError(
                            "Missing or invalid environment variable for "
                            f"HTTP header {header!r}"
                        )
                    headers[header] = os.environ[variable]
                if headers:
                    client = await stack.enter_async_context(
                        create_mcp_http_client(headers=headers)
                    )
                    streams = await stack.enter_async_context(
                        streamable_http_client(
                            self.config["url"], http_client=client
                        )
                    )
                else:
                    streams = await stack.enter_async_context(
                        streamable_http_client(self.config["url"])
                    )
            else:
                raise ValueError("MCP transport must be 'stdio' or 'http'")
            self.session = await stack.enter_async_context(
                ClientSession(*streams[:2])
            )
            await self.session.initialize()
        except BaseException:
            await stack.aclose()
            self.session = None
            raise
        self._stack = stack
        return self

    async def __aexit__(self, exc_type, exc, tb):
        try:
            return await self._stack.__aexit__(exc_type, exc, tb)
        finally:
            self._stack = None
            self.session = None

    async def _list(self, method, field):
        items = []
        cursor = None
        seen = set()
        while True:
            kwargs = (
                {"params": PaginatedRequestParams(cursor=cursor)}
                if cursor
                else {}
            )
            result = await getattr(self.session, method)(**kwargs)
            items.extend(getattr(result, field))
            cursor = result.next_cursor
            if not cursor:
                return items
            if cursor in seen:
                raise RuntimeError(
                    "MCP server returned a repeated pagination cursor"
                )
            seen.add(cursor)

    async def list_tools(self):
        return await self._list("list_tools", "tools")

    async def call_tool(self, name, arguments):
        return await self.session.call_tool(name, arguments)

    async def list_resources(self):
        return await self._list("list_resources", "resources")

    async def read_resource(self, uri):
        return await self.session.read_resource(uri)

    async def list_prompts(self):
        return await self._list("list_prompts", "prompts")

    async def get_prompt(self, name, arguments=None):
        return await self.session.get_prompt(name, arguments)


class MCPToolAdapter:
    """Expose one server's capabilities as LLM tool definitions and calls."""

    def __init__(self, server_name, connection):
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]+", server_name)
            or "__" in server_name
        ):
            raise ValueError("Invalid MCP server name")
        self.prefix = f"mcp__{server_name}__"
        self.connection = connection
        self._remote_tools = set()

    async def discover(self):
        remote = await self.connection.list_tools()
        reserved = {
            "list_resources",
            "read_resource",
            "list_prompts",
            "get_prompt",
        }
        self._remote_tools = set()
        tools = []
        for tool in remote:
            if (
                not re.fullmatch(r"[A-Za-z0-9_-]+", tool.name)
                or tool.name in reserved
                or tool.name in self._remote_tools
            ):
                raise ValueError(
                    f"Invalid or conflicting MCP tool name: {tool.name}"
                )
            self._remote_tools.add(tool.name)
            tools.append(
                llm.Tool(
                    name=self.prefix + tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
            )
        for name, description, properties, required in [
            ("list_resources", "List MCP server resources", {}, []),
            (
                "read_resource",
                "Read an MCP server resource",
                {"uri": {"type": "string"}},
                ["uri"],
            ),
            ("list_prompts", "List MCP server prompts", {}, []),
            (
                "get_prompt",
                "Get an MCP server prompt",
                {
                    "name": {"type": "string"},
                    "arguments": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                ["name"],
            ),
        ]:
            tools.append(
                llm.Tool(
                    name=self.prefix + name,
                    description=description,
                    input_schema={
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                )
            )
        return tools

    async def call(self, name, arguments):
        if not name.startswith(self.prefix):
            raise ValueError("Tool does not belong to this MCP server")
        local = name[len(self.prefix) :]
        if local in self._remote_tools:
            result = await self.connection.call_tool(local, arguments)
        elif local == "list_resources":
            result = await self.connection.list_resources()
        elif local == "read_resource":
            result = await self.connection.read_resource(arguments["uri"])
        elif local == "list_prompts":
            result = await self.connection.list_prompts()
        elif local == "get_prompt":
            result = await self.connection.get_prompt(
                arguments["name"], arguments.get("arguments")
            )
        else:
            raise ValueError(f"Unknown MCP tool: {name}")

        def serialize(value):
            return value.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )

        marker = "\n[output truncated]"
        limit = 50000
        chunks = []
        size = 0
        for chunk in json.JSONEncoder(default=serialize).iterencode(result):
            remaining = limit - size
            if len(chunk) > remaining:
                chunks.append(chunk[:remaining])
                return "".join(chunks)[: limit - len(marker)] + marker
            chunks.append(chunk)
            size += len(chunk)
        return "".join(chunks)
