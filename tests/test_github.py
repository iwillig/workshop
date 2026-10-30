import json

import httpx
from click.testing import CliRunner

from research_context import github
from workshop.cli import cli


def run_with_transport(monkeypatch, handler, args):
    real_client = httpx.Client
    monkeypatch.setattr(github.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return CliRunner().invoke(cli, ["research-context", "github", *args])


def test_list_issues_paginates_and_excludes_pull_requests(monkeypatch):
    def handler(request):
        assert request.url.params["state"] == "all"
        assert request.url.params["per_page"] == "100"
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[{"number": n} for n in range(99)] + [{"pull_request": {}}])
        return httpx.Response(200, json=[{"number": 100}])

    result = run_with_transport(monkeypatch, handler, ["list-issues", "owner/repo", "--state", "all"])
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.output)) == 100


def test_get_issue_includes_comments(monkeypatch):
    def handler(request):
        assert request.url.path in ("/repos/o/r/issues/7", "/repos/o/r/issues/7/comments")
        return httpx.Response(200, json=[{"body": "comment"}] if request.url.path.endswith("comments") else {"number": 7})

    result = run_with_transport(monkeypatch, handler, ["get-issue", "o/r", "7"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"issue": {"number": 7}, "comments": [{"body": "comment"}]}


def test_get_issue_rejects_pull_request(monkeypatch):
    result = run_with_transport(monkeypatch, lambda request: httpx.Response(200, json={"pull_request": {}}), ["get-issue", "o/r", "7"])
    assert result.exit_code != 0
    assert "get-pr" in result.output


def test_list_prs(monkeypatch):
    def handler(request):
        assert request.url.path == "/repos/o/r/pulls"
        assert request.url.params["state"] == "closed"
        return httpx.Response(200, json=[{"number": 2}])

    result = run_with_transport(monkeypatch, handler, ["list-prs", "o/r", "--state", "closed"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"number": 2}]


def test_search_prs_preserves_query_and_paginates(monkeypatch):
    query = "is:pr is:open draft:false review:none -author:@me"

    def handler(request):
        assert request.url.path == "/search/issues"
        assert request.url.params["q"] == f"is:pr {query}"
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"total_count": 101, "incomplete_results": page == 2, "items": [{"number": n} for n in (range(100) if page == 1 else [100])]})

    result = run_with_transport(monkeypatch, handler, ["search-prs", query])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["total_count"] == 101
    assert data["incomplete_results"] is True
    assert len(data["items"]) == 101


def test_search_prs_stops_at_github_search_limit(monkeypatch):
    pages = []
    def handler(request):
        pages.append(int(request.url.params["page"]))
        return httpx.Response(200, json={"total_count": 1200, "incomplete_results": False, "items": [{}] * 100})

    result = run_with_transport(monkeypatch, handler, ["search-prs", "is:open"])
    assert result.exit_code == 0, result.output
    assert pages == list(range(1, 11))
    assert len(json.loads(result.output)["items"]) == 1000


def test_get_pr_includes_discussion_and_reviews(monkeypatch):
    def handler(request):
        paths = {"/repos/o/r/pulls/2": {"number": 2}, "/repos/o/r/issues/2/comments": [{"id": 1}], "/repos/o/r/pulls/2/comments": [{"id": 2}], "/repos/o/r/pulls/2/reviews": [{"id": 3}]}
        return httpx.Response(200, json=paths[request.url.path])

    result = run_with_transport(monkeypatch, handler, ["get-pr", "o/r", "2"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"pull_request": {"number": 2}, "comments": [{"id": 1}], "review_comments": [{"id": 2}], "reviews": [{"id": 3}]}


def test_authentication_and_http_error(monkeypatch):
    real_client = httpx.Client
    def handler(request):
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(403, json={"message": "forbidden"})
    monkeypatch.setattr(github.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    result = CliRunner().invoke(cli, ["research-context", "github", "list-prs", "o/r"])
    assert result.exit_code != 0
    assert "HTTP 403" in result.output
    assert "secret" not in result.output


def test_invalid_repository_rejected(monkeypatch):
    result = CliRunner().invoke(cli, ["research-context", "github", "list-prs", "o/../other"])
    assert result.exit_code != 0
    assert "OWNER/REPO" in result.output


def test_network_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("offline", request=request)
    result = run_with_transport(monkeypatch, handler, ["list-prs", "o/r"])
    assert result.exit_code != 0
    assert "Could not connect to GitHub" in result.output
