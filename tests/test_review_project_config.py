import pytest

from workshop.config import load_workshop_config


def test_project_review_settings(tmp_path):
    path = tmp_path / "workshop.yaml"
    path.write_text(
        "git: {base_ref: main}\n"
        "github:\n  repositories: {app: owner/repo}\n"
        "  default_repo: app\n"
    )
    config = load_workshop_config(path)
    assert config["git"] == {"base_ref": "main"}
    assert config["github"] == {
        "repositories": {"app": "owner/repo"}, "default_repo": "app"
    }


def test_resolve_github_repository():
    from workshop.config import resolve_github_repository

    project = {"github": {"repositories": {"app": "owner/repo"},
                          "default_repo": "app"}}
    assert resolve_github_repository(project) == "owner/repo"
    assert resolve_github_repository(project, "app") == "owner/repo"
    assert (
        resolve_github_repository(project, "other/project") == "other/project"
    )
    with pytest.raises(ValueError, match="repository"):
        resolve_github_repository({}, None)
    with pytest.raises(ValueError, match="repository"):
        resolve_github_repository(project, "missing")


def test_github_native_tool_uses_project_default(monkeypatch):
    import json
    from research_context import github_tools

    class Service:
        def get_pr(self, repository, number):
            return {"repository": repository, "number": number}

        def close(self):
            pass

    monkeypatch.setattr(github_tools, "GitHubReviewService", Service)
    provider = github_tools.GitHubTools(
        {"github_get_pr"},
        project={"github": {"repositories": {"app": "owner/repo"},
                            "default_repo": "app"}},
    )
    result = provider.execute(
        {"tool": "github_get_pr", "arguments": {"number": 42}}
    )
    assert result["returncode"] == 0
    assert json.loads(result["output"])["repository"] == "owner/repo"
    schema = provider.tools[0].input_schema
    assert "repository" not in schema["required"]


def test_github_cli_default_and_explicit_repository(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from research_context import github
    from workshop.cli import cli

    config = tmp_path / "workshop.yaml"
    config.write_text(
        "github:\n  repositories: {app: owner/repo}\n"
        "  default_repo: app\n"
    )
    paths = []

    class API:
        def get(self, path, params=None):
            paths.append(path)
            return {}

        def list_all(self, path, params=None):
            paths.append(path)
            return []

    monkeypatch.setattr(github, "github_request", lambda fn: fn(API()))
    runner = CliRunner()
    prefix = ["--workshop-config", str(config), "research-context", "github"]
    for args, expected in [
        (["get-pr", "123"], "/repos/owner/repo/pulls/123"),
        (["get-pr", "other/project", "123"], "/repos/other/project/pulls/123"),
        (["list-prs"], "/repos/owner/repo/pulls"),
        (["list-prs", "app"], "/repos/owner/repo/pulls"),
    ]:
        paths.clear()
        result = runner.invoke(cli, prefix + args)
        assert result.exit_code == 0, result.output
        assert expected in paths


def test_standalone_research_context_discovers_and_selects_config(
    tmp_path, monkeypatch
):
    from click.testing import CliRunner
    from research_context import github
    from research_context.__main__ import cli

    (tmp_path / "workshop.yaml").write_text(
        "github: {repositories: {a: owner/repo}, default_repo: a}\n"
    )
    other = tmp_path / "other.yaml"
    other.write_text(
        "github: {repositories: {b: other/repo}, default_repo: b}\n"
    )
    monkeypatch.chdir(tmp_path)
    paths = []

    class API:
        def list_all(self, path, params=None):
            paths.append(path)
            return []

    monkeypatch.setattr(github, "github_request", lambda fn: fn(API()))
    runner = CliRunner()
    result = runner.invoke(cli, ["github", "list-prs"])
    assert result.exit_code == 0, result.output
    assert paths[-1] == "/repos/owner/repo/pulls"
    result = runner.invoke(
        cli, ["--workshop-config", str(other), "github", "list-prs"]
    )
    assert result.exit_code == 0, result.output
    assert paths[-1] == "/repos/other/repo/pulls"


@pytest.mark.parametrize(
    "content",
    [
        "git: {base_ref: ''}",
        "git: {base_ref: 123}",
        "git: {unknown: value}",
        "github: {repositories: {app: invalid}}",
        "github: {repositories: {app: owner/repo}, default_repo: other}",
        "github: {repositories: {'bad alias': owner/repo}}",
        "github: {unknown: value}",
    ],
)
def test_invalid_project_review_settings(tmp_path, content):
    path = tmp_path / "workshop.yaml"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_workshop_config(path)
