import json

from click.testing import CliRunner

from research_context import __main__ as research
from workshop.cli import cli


def test_help_hierarchy():
    runner = CliRunner()
    for args, expected in [
        ([], "research-context"),
        (["research-context"], "asana"),
        (["research-context", "asana"], "list-tasks"),
    ]:
        result = runner.invoke(cli, [*args, "--help"])
        assert result.exit_code == 0
        assert expected in result.output


def test_commands_through_workshop(monkeypatch):
    class API:
        def get_tasks_for_project(self, project_gid, opts, **kwargs):
            assert project_gid == "123"
            return iter([{"gid": "42"}])

        def get_task(self, task_gid, opts, **kwargs):
            assert task_gid == "42"
            return {"data": {"gid": "42"}}

    monkeypatch.setattr(research, "tasks_api", lambda: API())
    runner = CliRunner()
    result = runner.invoke(
        cli, ["research-context", "asana", "list-tasks", "123"]
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == [{"gid": "42"}]
    result = runner.invoke(
        cli, ["research-context", "asana", "get-task", "42"]
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == {"gid": "42"}


def test_missing_token_through_workshop(monkeypatch):
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    result = CliRunner().invoke(
        cli, ["research-context", "asana", "get-task", "42"]
    )
    assert result.exit_code != 0
    assert "ASANA_ACCESS_TOKEN" in result.output
