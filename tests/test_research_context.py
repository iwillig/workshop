import json

from click.testing import CliRunner
from asana.rest import ApiException

from research_context import __main__ as app


def test_list_tasks(monkeypatch):
    class API:
        def get_tasks_for_project(self, project_gid, opts, **kwargs):
            assert project_gid == "123"
            assert opts["opt_fields"] == "gid,name,completed"
            return iter([{"gid": "1", "name": "Task", "completed": False}])

    monkeypatch.setattr(app, "tasks_api", lambda: API())
    result = CliRunner().invoke(app.cli, ["asana", "list-tasks", "123"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {"gid": "1", "name": "Task", "completed": False}
    ]


def test_get_task(monkeypatch):
    class API:
        def get_task(self, task_gid, opts, **kwargs):
            assert task_gid == "42"
            assert kwargs["full_payload"] is True
            return {"data": {"gid": "42", "name": "Task"}}

    monkeypatch.setattr(app, "tasks_api", lambda: API())
    result = CliRunner().invoke(app.cli, ["asana", "get-task", "42"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"gid": "42", "name": "Task"}


def test_missing_token(monkeypatch):
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    result = CliRunner().invoke(app.cli, ["asana", "get-task", "42"])
    assert result.exit_code != 0
    assert "ASANA_ACCESS_TOKEN" in result.output


def test_api_error(monkeypatch):
    class API:
        def get_task(self, *args, **kwargs):
            raise ApiException(status=403, reason="Forbidden")

    monkeypatch.setattr(app, "tasks_api", lambda: API())
    result = CliRunner().invoke(app.cli, ["asana", "get-task", "42"])
    assert result.exit_code != 0
    assert "HTTP 403" in result.output
