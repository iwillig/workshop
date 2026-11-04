import base64
from pathlib import Path

import httpx

from workshop.agent.config import build_agent, load_config


BASE = "a" * 40
HEAD = "b" * 40


def handler(request):
    path = request.url.path
    if path == "/repos/o/r/pulls/1":
        return httpx.Response(
            200,
            json={
                "number": 1,
                "title": "PR",
                "body": "Fix it",
                "html_url": "https://github.com/o/r/pull/1",
                "state": "open",
                "base": {"sha": BASE, "ref": "main"},
                "head": {"sha": HEAD, "ref": "branch"},
                "changed_files": 1,
            },
        )
    if path.endswith("/pulls/1/files"):
        return httpx.Response(
            200,
            json=[
                {
                    "filename": "a.py",
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
        )
    if path.endswith("/contents/a.py"):
        content = base64.b64encode(b"new\n").decode()
        return httpx.Response(
            200,
            json={
                "type": "file",
                "encoding": "base64",
                "content": content,
            },
        )
    return httpx.Response(404)


def fake_service():
    from research_context.github_review import GitHubReviewService

    return GitHubReviewService(
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.github.com",
        )
    )


def test_example_agent_uses_only_github_read_tools(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model",
        lambda _: SimpleNamespace(conversation=lambda: object()),
    )
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "pr-review-agent.yaml"
    )
    config = load_config(path, agent_name="pr-reviewer")
    assert "system_template" in config["agent"]
    agent = build_agent(config)
    builtins = [tool.name for tool in agent.builtin_tools.tools]
    research = [tool.name for tool in agent.tool_providers[0].tools]
    assert not builtins
    assert set(research) == {
        "github_get_pr",
        "github_pr_files",
        "github_read_file",
    }
    assert agent.mcp_runtime is None
    assert agent.model.config.protocol == "native"
    assert agent.config.step_limit == 20


def test_reviewer_uses_tools_and_reports_shas(monkeypatch):
    import llm

    from research_context import github_tools

    calls = []
    responses = [
        llm.ToolCall(
            name="github_get_pr",
            arguments={"repository": "o/r", "number": 1},
            tool_call_id="one",
        ),
        llm.ToolCall(
            name="github_pr_files",
            arguments={
                "repository": "o/r",
                "number": 1,
                "base_sha": BASE,
                "head_sha": HEAD,
            },
            tool_call_id="two",
        ),
        llm.ToolCall(
            name="github_read_file",
            arguments={"repository": "o/r", "path": "a.py", "sha": HEAD},
            tool_call_id="three",
        ),
    ]

    class Conversation:
        def __init__(self):
            self.responses = []

        def prompt(self, prompt, **kwargs):
            index = len(self.responses)
            if index < len(responses):
                content, call = "", [responses[index]]
            else:
                content, call = "Review done", []
            self.responses.append(content)
            calls.append(call[0].name if call else None)
            return type(
                "Response",
                (),
                {
                    "text": lambda self: content,
                    "tool_calls": lambda self: call,
                    "usage": lambda self: None,
                },
            )()

    class Backend:
        def conversation(self):
            return Conversation()

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend()
    )
    monkeypatch.setattr(github_tools, "GitHubReviewService", fake_service)
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "pr-review-agent.yaml"
    )
    agent = build_agent(load_config(path, agent_name="pr-reviewer"))
    result = agent.run("Review o/r pull request 1")
    assert result["exit_status"] == "Submitted"
    assert result["submission"] == "Review done"
    assert calls[:3] == [
        "github_get_pr",
        "github_pr_files",
        "github_read_file",
    ]
    assert all(name is None for name in calls[3:])


def test_github_tools_absent_without_explicit_selection(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model",
        lambda _: SimpleNamespace(conversation=lambda: object()),
    )
    agent = build_agent({"model": {"protocol": "native"}})
    assert agent.tool_providers == []


def test_tool_collisions_rejected():
    agent = build_agent(
        {
            "model": {"protocol": "native"},
            "tools": {"read": {}, "github_get_pr": {}},
        }
    )
    names = [tool.name for tool in agent.builtin_tools.tools]
    assert "read" in names
    assert all(
        tool.name not in names for tool in agent.tool_providers[0].tools
    )
