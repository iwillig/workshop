import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from research_context.github_review import GitHubReviewService

BASE = "a" * 40
HEAD = "b" * 40


def canned():
    return {
        "/repos/loopback/example/pulls/7": {
            "number": 7,
            "title": "Fix ranges",
            "body": "Adjust page math",
            "base": {"sha": BASE, "ref": "main"},
            "head": {"sha": HEAD, "ref": "fix"},
        }
    }


def serve(responses):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path in responses:
                body = json.dumps(responses[self.path]).encode()
            else:
                body = b"{}"
            self.send_response(200 if self.path in responses else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_env_override_routes_to_loopback(monkeypatch):
    responses = canned()
    server, url = serve(responses)
    monkeypatch.setenv("WORKSHOP_GITHUB_API_BASE", url)
    try:
        service = GitHubReviewService()
        try:
            pr = service.get_pr("loopback/example", 7)
            assert pr["head_sha"] == HEAD
        finally:
            service.close()
    finally:
        server.shutdown()


def test_env_override_rejects_non_loopback(monkeypatch):
    for url in ("https://example.com", "http://10.0.0.1:1", "not-a-url"):
        monkeypatch.setenv("WORKSHOP_GITHUB_API_BASE", url)
        with pytest.raises(ValueError, match="loopback"):
            GitHubReviewService()


def test_default_base_unchanged_without_override(monkeypatch):
    monkeypatch.delenv("WORKSHOP_GITHUB_API_BASE", raising=False)
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        "research_context.github_review.httpx.Client", FakeClient
    )
    GitHubReviewService()
    assert captured["base_url"] == "https://api.github.com"


def test_pr_review_suite_loads_with_pinned_fixture():
    from workshop.agent_benchmark.local import load_suite

    suite = load_suite("pr-review-v4")
    assert suite.suite.role == "pr-review"
    assert [entry.case.id for entry in suite.cases] == [
        "range-off-by-one",
        "benign-rename",
    ]
    for entry in suite.cases:
        assert entry.case.scoring_method == "human-review"
        assert (entry.fixture / "github.json").exists()


def test_pr_review_suite_fingerprint_is_stable():
    from workshop.agent_benchmark.local import load_suite

    assert load_suite("pr-review-v4").sha256 == (
        "4fb24fbbf7d28d231be8fd91b2c59247aac4946a557da69122edd1e5c272e4eb"
    )
    # Existing suites must keep their pinned fingerprints.
    assert load_suite("review-v3").sha256 == (
        "e278d1cb2ddfdacb8c4c7d5cb5e806f84c66e272b5f07571624900cd94450aa5"
    )
    assert load_suite("coding-v1").sha256 == (
        "1581dfca2daa6805af28cc20807fda85247c9527d72d087d85f088336850cc16"
    )


def test_pr_review_run_serves_loopback_and_restores_env(tmp_path):
    from workshop.agent_benchmark.local import run_suite

    seen = {}

    def execute(task, workspace, config):
        seen["env"] = os.environ.get("WORKSHOP_GITHUB_API_BASE")
        seen["task"] = task
        return {"exit_status": "Submitted", "submission": "No findings."}

    before = os.environ.get("WORKSHOP_GITHUB_API_BASE")
    report = run_suite(
        "pr-review-v4",
        {},
        "reviewer",
        tmp_path / "private",
        local=True,
        execute=execute,
    )
    outcomes = {
        case["case_id"]: case["outcome"] for case in report["run"]["results"]
    }
    assert outcomes == {
        "range-off-by-one": "pending_human_review",
        "benign-rename": "pending_human_review",
    }
    assert seen["env"] and seen["env"].startswith("http://127.0.0.1:")
    assert os.environ.get("WORKSHOP_GITHUB_API_BASE") == before
    assert "loopback" in seen["task"]


def test_pr_review_run_rejects_unacknowledged_local():
    from workshop.agent_benchmark.local import run_suite

    with pytest.raises(ValueError, match="local"):
        run_suite("pr-review-v4", {}, "r", "/tmp/unused", local=False)


def test_pr_review_run_with_real_tools_against_loopback(tmp_path):
    """End-to-end: github tools run through the loopback fixture server."""
    import llm

    import workshop.agent.models as models
    from workshop.agent_benchmark.local import run_suite

    class Conversation:
        def __init__(self):
            self.responses = []
            self.number = None

        def prompt(self, prompt, **kwargs):
            index = len(self.responses)
            if self.number is None:
                self.number = 9 if prompt and "pull request 9" in prompt else 7
            number = self.number
            paths = {
                7: ("ranges.py", "b" * 40, "page_count is off by one"),
                9: ("paging.py", "d" * 40, "No verified findings."),
            }
            path, sha, final = paths[number]
            if index == 0:
                call = llm.ToolCall(
                    name="github_get_pr",
                    arguments={
                        "repository": "loopback/example",
                        "number": number,
                    },
                    tool_call_id="one",
                )
                content, calls = "", [call]
            elif index == 1:
                assert sha in kwargs["tool_results"][0].output
                call = llm.ToolCall(
                    name="github_read_file",
                    arguments={
                        "repository": "loopback/example",
                        "path": path,
                        "sha": sha,
                    },
                    tool_call_id="two",
                )
                content, calls = "", [call]
            else:
                content, calls = final, []
            self.responses.append(content)
            return type(
                "Response",
                (),
                {
                    "text": lambda self: content,
                    "tool_calls": lambda self: calls,
                    "usage": lambda self: None,
                },
            )()

    class Backend:
        def conversation(self):
            return Conversation()

    config = {
        "agent": {"agent_class": "default", "step_limit": 4},
        "model": {"protocol": "native"},
        "environment": {},
        "tools": {
            "github_get_pr": {},
            "github_pr_files": {},
            "github_read_file": {},
        },
    }
    original = models.llm.get_model
    models.llm.get_model = lambda _: Backend()
    try:
        report = run_suite(
            "pr-review-v4",
            config,
            "reviewer",
            tmp_path / "private",
            local=True,
            capture_trace=True,
        )
    finally:
        models.llm.get_model = original
    details = {case["case_id"]: case for case in report["details"]}
    assert "page_count" in details["range-off-by-one"]["findings"]
    assert details["benign-rename"]["findings"] is not None
    trace = report["run"]["trace"]
    assert trace is not None and trace["format"]
