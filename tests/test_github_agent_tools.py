import base64
import json

import httpx
import pytest


BASE = "a" * 40
HEAD = "b" * 40


def transport_handler(request):
    assert request.method == "GET"
    path = request.url.path
    pr = {
        "number": 1,
        "title": "PR",
        "body": "context",
        "base": {"sha": BASE, "ref": "main"},
        "head": {"sha": HEAD, "ref": "branch"},
        "changed_files": 1,
    }
    if path == "/repos/o/r/pulls/1":
        return httpx.Response(200, json=pr)
    if path.endswith("/pulls/1/files"):
        return httpx.Response(
            200,
            json=[{"filename": "a.py", "status": "modified", "patch": "+new"}],
        )
    if path.endswith("/contents/a.py"):
        assert request.url.params["ref"] == HEAD
        return httpx.Response(
            200,
            json={
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(b"hello\nworld\n").decode(),
            },
        )
    return httpx.Response(404)


def service():
    from research_context.github_review import GitHubReviewService

    return GitHubReviewService(
        client=httpx.Client(
            transport=httpx.MockTransport(transport_handler),
            base_url="https://api.github.com",
        )
    )


def test_shared_service_fetches_pinned_pr_and_source():
    api = service()
    pr = api.get_pr("o/r", 1)
    assert pr["head_sha"] == HEAD
    files = api.pr_files("o/r", 1, BASE, HEAD)
    assert files["files"][0]["patch"] == "+new"
    source = api.read_file("o/r", "a.py", HEAD, offset=2, limit=1)
    assert source["content"] == "world\n"
    assert source["complete"] is True
    api.close()


def test_stale_and_invalid_inputs():
    api = service()
    with pytest.raises(ValueError, match="changed"):
        api.pr_files("o/r", 1, BASE, "c" * 40)
    for path in ("../secret", "/absolute", "a/../b"):
        with pytest.raises(ValueError):
            api.read_file("o/r", path, HEAD)
    with pytest.raises(ValueError):
        api.read_file("o/r", "a.py", "main")
    api.close()


def test_tool_selection_is_explicit_and_dispatches(monkeypatch):
    from types import SimpleNamespace
    from workshop.agent_config import build_agent
    from research_context import github_tools

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model",
        lambda _: SimpleNamespace(conversation=lambda: object()),
    )
    monkeypatch.setattr(github_tools, "GitHubReviewService", service)
    config = {
        "model": {"protocol": "native"},
        "agent": {"agent_class": "default"},
        "tools": {"github_get_pr": {}},
    }
    agent = build_agent(config)
    assert [t.name for t in agent.tool_providers[0].tools] == ["github_get_pr"]
    output = agent.tool_providers[0].execute(
        {
            "tool": "github_get_pr",
            "arguments": {"repository": "o/r", "number": 1},
        }
    )
    assert json.loads(output["output"])["head_sha"] == HEAD
    assert output["returncode"] == 0
    other = build_agent({"model": {"protocol": "native"}})
    assert not other.tool_providers


def test_tool_errors_are_bounded_and_sanitized(monkeypatch):
    from research_context.github_tools import GitHubTools

    tools = GitHubTools({"github_get_pr"})
    result = tools.execute(
        {
            "tool": "github_get_pr",
            "arguments": {"repository": "../r", "number": 1},
        }
    )
    assert result["returncode"] != 0
    assert json.loads(result["output"])["error"]
    assert len(result["output"]) < 50000
