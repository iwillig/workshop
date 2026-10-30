"""Read GitHub issues and pull requests for research and context."""

import json
import os

import click
import httpx


class GitHubAPI:
    def __init__(self):
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30, follow_redirects=False)

    def get(self, path, params=None):
        response = self.client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def list_all(self, path, params=None):
        items = []
        page = 1
        while True:
            batch = self.get(path, {**(params or {}), "per_page": 100, "page": page})
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1


def repository_path(repository):
    parts = repository.split("/")
    if len(parts) != 2 or any(not part or part in (".", "..") or not all(c.isascii() and (c.isalnum() or c in "-_.") for c in part) for part in parts):
        raise click.BadParameter("Use OWNER/REPO.")
    return f"/repos/{repository}"


def github_request(operation):
    api = GitHubAPI()
    try:
        return operation(api)
    except httpx.HTTPStatusError as exc:
        raise click.ClickException(f"GitHub request failed (HTTP {exc.response.status_code}).") from exc
    except httpx.RequestError as exc:
        raise click.ClickException("Could not connect to GitHub.") from exc
    finally:
        api.client.close()


def output(value):
    click.echo(json.dumps(value, indent=2))


@click.group(name="github")
def github_commands():
    """Read GitHub issues and pull requests."""


@github_commands.command("list-issues")
@click.argument("repository")
@click.option("--state", type=click.Choice(["open", "closed", "all"]), default="open", show_default=True)
def list_issues(repository, state):
    """List issues in OWNER/REPO as JSON, excluding pull requests."""
    path = repository_path(repository)
    issues = github_request(lambda api: api.list_all(f"{path}/issues", {"state": state}))
    output([issue for issue in issues if "pull_request" not in issue])


@github_commands.command("get-issue")
@click.argument("repository")
@click.argument("number", type=click.IntRange(min=1))
def get_issue(repository, number):
    """Get an issue and its comments from OWNER/REPO as JSON."""
    path = repository_path(repository)

    def fetch(api):
        issue = api.get(f"{path}/issues/{number}")
        if "pull_request" in issue:
            raise click.ClickException("That number is a pull request; use get-pr instead.")
        return {"issue": issue, "comments": api.list_all(f"{path}/issues/{number}/comments")}

    output(github_request(fetch))


@github_commands.command("list-prs")
@click.argument("repository")
@click.option("--state", type=click.Choice(["open", "closed", "all"]), default="open", show_default=True)
def list_prs(repository, state):
    """List pull requests in OWNER/REPO as JSON."""
    path = repository_path(repository)
    output(github_request(lambda api: api.list_all(f"{path}/pulls", {"state": state})))


@github_commands.command("search-prs")
@click.argument("query")
def search_prs(query):
    """Search pull requests with a GitHub search QUERY as JSON."""
    def fetch(api):
        items = []
        page = 1
        total_count = 0
        incomplete_results = False
        while True:
            result = api.get("/search/issues", {"q": f"is:pr {query}", "per_page": 100, "page": page})
            total_count = result["total_count"]
            incomplete_results = incomplete_results or result["incomplete_results"]
            batch = result["items"]
            items.extend(batch)
            if len(batch) < 100 or len(items) >= min(total_count, 1000):
                return {"total_count": total_count, "incomplete_results": incomplete_results, "items": items}
            page += 1

    output(github_request(fetch))


@github_commands.command("get-pr")
@click.argument("repository")
@click.argument("number", type=click.IntRange(min=1))
def get_pr(repository, number):
    """Get a pull request, comments and reviews from OWNER/REPO as JSON."""
    path = repository_path(repository)

    def fetch(api):
        return {
            "pull_request": api.get(f"{path}/pulls/{number}"),
            "comments": api.list_all(f"{path}/issues/{number}/comments"),
            "review_comments": api.list_all(f"{path}/pulls/{number}/comments"),
            "reviews": api.list_all(f"{path}/pulls/{number}/reviews"),
        }

    output(github_request(fetch))
