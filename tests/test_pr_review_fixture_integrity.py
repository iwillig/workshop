import base64
import difflib
import json

import pytest

from research_context.github_review import GitHubReviewService
from workshop.agent_benchmark.local import load_suite, run_suite


def source(fixture, path, sha):
    response = fixture[f"/repos/loopback/example/contents/{path}?ref={sha}"]
    raw = base64.b64decode(response["content"], validate=True)
    assert response["size"] == len(raw)
    code = raw.decode("utf-8")
    namespace = {}
    exec(compile(code, path, "exec"), namespace)
    return code, namespace


def test_corrected_fixtures_are_valid_consistent_and_distinct():
    suite = load_suite("pr-review-v5")
    assert len(suite.cases) == 2
    for entry in suite.cases:
        fixture = json.loads((entry.fixture / "github.json").read_text())
        number = 7 if "range" in entry.case.id else 9
        pr_path = f"/repos/loopback/example/pulls/{number}"
        pr = fixture[pr_path]
        files = fixture[f"{pr_path}/files?per_page=5&page=1"]
        file = files[0]
        base, base_ns = source(
            fixture,
            file.get("previous_filename", file["filename"]),
            pr["base"]["sha"],
        )
        head, head_ns = source(fixture, file["filename"], pr["head"]["sha"])
        if number == 7:
            patch = "".join(
                list(
                    difflib.unified_diff(
                        base.splitlines(keepends=True),
                        head.splitlines(keepends=True),
                        fromfile="a/ranges.py",
                        tofile="b/ranges.py",
                        n=3,
                    )
                )[2:]
            )
            assert file["patch"] == patch
            for count, expected in [(0, 0), (1, 1), (4, 1), (5, 2), (8, 2)]:
                assert base_ns["page_count"](list(range(count)), 4) == expected
            assert head_ns["page_count"]([1, 2, 3, 4], 4) == 0
        else:
            assert base == head
            assert file["status"] == "renamed"
            assert file["previous_filename"] != file["filename"]
            assert "patch" not in file
            assert head_ns["page_count"]([1, 2, 3, 4], 4) == 1


def test_v5_fingerprint_and_tampering(tmp_path, monkeypatch):
    import shutil
    import workshop.agent_benchmark.local as local

    assert load_suite("pr-review-v5").sha256 == (
        "415df457cc7a2dfbc78fc0afc3487ba5fa1f665767f0f5c05587b69d9c9317c6"
    )
    shutil.copytree(local._ROOT / "fixtures", tmp_path / "fixtures")
    shutil.copytree(local._ROOT / "checks", tmp_path / "checks")
    path = tmp_path / "fixtures/pr-review-range-v2/github.json"
    path.write_text(path.read_text() + " ")
    monkeypatch.setattr(local, "_ROOT", tmp_path)
    with pytest.raises(ValueError, match="Fixture hash mismatch"):
        load_suite("pr-review-v5")


def test_old_suite_preserved_but_cannot_be_run(tmp_path):
    assert load_suite("pr-review-v4").sha256 == (
        "4fb24fbbf7d28d231be8fd91b2c59247aac4946a557da69122edd1e5c272e4eb"
    )
    with pytest.raises(ValueError, match="invalid|defective"):
        run_suite("pr-review-v4", {}, "reviewer", tmp_path, local=True)


def test_loopback_override_never_sends_github_token(monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            payload = json.dumps(
                {
                    "base": {"sha": "a" * 40},
                    "head": {"sha": "b" * 40},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setenv(
        "WORKSHOP_GITHUB_API_BASE", f"http://127.0.0.1:{server.server_port}"
    )
    try:
        api = GitHubReviewService()
        try:
            api.get_pr("loopback/example", 7)
        finally:
            api.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert seen == [None]


def test_loopback_client_disables_proxy_configuration(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("WORKSHOP_GITHUB_API_BASE", "http://127.0.0.1:1234")
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setattr(
        "research_context.github_review.httpx.Client", FakeClient
    )
    GitHubReviewService()
    assert captured["trust_env"] is False
    assert "Authorization" not in captured["headers"]


def test_normal_github_client_keeps_token_and_proxy_behavior(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.delenv("WORKSHOP_GITHUB_API_BASE", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    monkeypatch.setattr(
        "research_context.github_review.httpx.Client", FakeClient
    )
    GitHubReviewService()
    assert captured["base_url"] == "https://api.github.com"
    assert captured["headers"]["Authorization"] == "Bearer not-a-real-token"
    assert "trust_env" not in captured


def test_v5_tools_retrieve_each_fixture_without_credentials(monkeypatch):
    from workshop.agent_benchmark.pr_fixture import FixtureServer

    monkeypatch.setenv("GITHUB_TOKEN", "not-a-real-token")
    for entry in load_suite("pr-review-v5").cases:
        fixture = json.loads((entry.fixture / "github.json").read_text())
        number = 7 if "range" in entry.case.id else 9
        with FixtureServer(fixture) as server:
            monkeypatch.setenv("WORKSHOP_GITHUB_API_BASE", server.base_url)
            service = GitHubReviewService()
            try:
                pr = service.get_pr("loopback/example", number)
                files = service.pr_files(
                    "loopback/example", number, pr["base_sha"], pr["head_sha"]
                )
                file = files["files"][0]
                head = service.read_file(
                    "loopback/example", file["path"], pr["head_sha"]
                )
                base = service.read_file(
                    "loopback/example",
                    file["previous_path"] or file["path"],
                    pr["base_sha"],
                )
                assert "def page_count" in head["content"]
                if number == 7:
                    assert file["patch_available"]
                    assert base["content"] != head["content"]
                else:
                    assert not file["patch_available"]
                    assert base["content"] == head["content"]
            finally:
                service.close()


def test_v5_report_needs_human_review(tmp_path):
    report = run_suite(
        "pr-review-v5",
        {},
        "reviewer",
        tmp_path / "private",
        local=True,
        execute=lambda *args: {"exit_status": "Submitted", "submission": "ok"},
    )
    assert report["counts"]["pending_human_review"] == 2
    assert all(case["expected_findings"] for case in report["details"])
