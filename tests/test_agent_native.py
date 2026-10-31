import sys

import llm

from workshop.agent.config import build_agent

from workshop.agent.models import LlmModel


class Response:
    def __init__(self, content, calls):
        self.content = content
        self.calls = calls

    def text(self):
        return self.content

    def tool_calls(self):
        return self.calls

    def usage(self):
        return type("Usage", (), {"input": 0, "output": 0})()


class Conversation:
    def __init__(self):
        self.responses = []
        self.requests = []

    def prompt(self, prompt, **kwargs):
        self.requests.append((prompt, kwargs))
        calls = (
            [
                llm.ToolCall(
                    name="mcp__demo__echo",
                    arguments={"text": "hi"},
                    tool_call_id="call-1",
                )
            ]
            if not self.responses
            else []
        )
        response = Response("done" if not calls else "", calls)
        self.responses.append(response)
        return response


class Backend:
    def conversation(self):
        return Conversation()


def test_agent_calls_real_mcp_server_and_submits(tmp_path, monkeypatch):
    server = tmp_path / "server.py"
    server.write_text("""\
from mcp.server.mcpserver import MCPServer
server = MCPServer("test")
@server.tool()
def echo(text: str) -> str:
    return text
if __name__ == "__main__":
    server.run(transport="stdio")
""")
    monkeypatch.setattr("workshop.agent.models.llm.get_model", lambda _: Backend())
    agent = build_agent(
        {
            "agent": {
                "agent_class": "default",
                "system_template": "sys",
                "instance_template": "{{ task }}",
            },
            "model": {"protocol": "native", "retry_attempts": 1},
            "environment": {"environment_class": "local"},
            "mcp_servers": {
                "demo": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(server)],
                }
            },
        }
    )
    result = agent.run("task")
    assert result["exit_status"] == "Submitted"
    assert result["submission"] == "done"
    assert "hi" in agent.model._conversation.requests[1][1]["tool_results"][0].output
    names = {tool.name for tool in agent.model._conversation.requests[0][1]["tools"]}
    assert {"read", "edit", "bash", "mcp__demo__echo"} <= names
    assert agent.run("second task")["exit_status"] == "Submitted"


def test_native_agent_executes_builtin_read_without_mcp(tmp_path, monkeypatch):
    (tmp_path / "sample.txt").write_text("contents")

    class ReadConversation(Conversation):
        def prompt(self, prompt, **kwargs):
            response = super().prompt(prompt, **kwargs)
            if response.calls:
                response.calls = [
                    llm.ToolCall(
                        name="read",
                        arguments={"path": "sample.txt"},
                        tool_call_id="read-1",
                    )
                ]
            return response

    class ReadBackend:
        def conversation(self):
            return ReadConversation()

    monkeypatch.setattr("workshop.agent.models.llm.get_model", lambda _: ReadBackend())
    agent = build_agent(
        {
            "agent": {"agent_class": "default"},
            "environment": {"cwd": str(tmp_path)},
            "model": {"protocol": "native"},
        }
    )
    assert agent.run("read file")["exit_status"] == "Submitted"
    assert (
        agent.model._conversation.requests[1][1]["tool_results"][0].output == "contents"
    )


def test_native_model_passes_tool_calls_and_results(monkeypatch):
    monkeypatch.setattr("workshop.agent.models.llm.get_model", lambda _: Backend())
    model = LlmModel(protocol="native", retry_attempts=1)
    model.native_tools = [
        llm.Tool(name="mcp__demo__echo", input_schema={"type": "object"})
    ]
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
    ]
    response = model.query(messages)
    action = response["extra"]["actions"][0]
    assert action == {
        "tool": "mcp__demo__echo",
        "arguments": {"text": "hi"},
        "tool_call_id": "call-1",
    }
    outputs = [{"output": "hi", "returncode": 0, "exception_info": ""}]
    messages += [response, *model.format_observation_messages(response, outputs)]
    final = model.query(messages)
    assert final["extra"]["native_final"] is True
    assert model._conversation.requests[0][1]["tools"] == model.native_tools
    result = model._conversation.requests[1][1]["tool_results"][0]
    assert result.name == "mcp__demo__echo"
    assert result.tool_call_id == "call-1"
    assert result.output == "hi"
