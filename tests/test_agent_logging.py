import os
import sqlite3
from types import SimpleNamespace

import pytest

from workshop.agent.models import LlmModel


class Response:
    def text(self):
        return "done"

    def usage(self):
        return SimpleNamespace(input=1, output=1)

    def tool_calls(self):
        return []

    def log_to_db(self, db):
        db.execute("CREATE TABLE IF NOT EXISTS calls (text TEXT)")
        db.execute("INSERT INTO calls VALUES ('logged')")
        db.conn.commit()


class Conversation:
    def __init__(self):
        self.responses = []

    def prompt(self, *args, **kwargs):
        response = Response()
        self.responses.append(response)
        return response


class Backend:
    def conversation(self):
        return Conversation()


def test_logging_is_opt_in_and_private(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend()
    )
    path = tmp_path / "private" / "logs.db"
    messages = [{"role": "user", "content": "hi"}]
    model = LlmModel(protocol="native")
    model.query(messages)
    assert not path.exists()
    model.configure_log_database(path)
    model.reset()
    model.query(messages)
    assert (
        sqlite3.connect(path)
        .execute("SELECT count(*) FROM calls")
        .fetchone()[0]
        == 1
    )
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0
        assert path.parent.stat().st_mode & 0o077 == 0


def test_real_llm_log_contains_native_tool_round_trip(tmp_path, monkeypatch):
    import llm

    class FakeModel(llm.Model):
        model_id = "fake-logging-model"

        def execute(self, prompt, stream, response, conversation):
            if not conversation.responses:
                response.add_tool_call(
                    llm.ToolCall(
                        name="read",
                        arguments={"path": "a.txt"},
                        tool_call_id="call1",
                    )
                )
                yield "reading"
            else:
                yield "done"

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: FakeModel()
    )
    model = LlmModel(protocol="native", retry_attempts=1)
    path = tmp_path / "logs.db"
    model.configure_log_database(path)
    messages = [
        {"role": "system", "content": "system secret"},
        {"role": "user", "content": "task secret"},
    ]
    first = model.query(messages)
    observations = model.format_observation_messages(
        first, [{"output": "tool secret"}]
    )
    model.query(messages + [first] + observations)
    db = sqlite3.connect(path)
    assert db.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 2
    text = " ".join(
        str(row) for row in db.execute("SELECT type, text, payload FROM parts")
    )
    assert "task secret" in text and "tool secret" in text and "read" in text
    db.close()


def test_supervised_worker_uses_configured_log_database(tmp_path, monkeypatch):
    from workshop.agent.supervised import SupervisedAgent

    module = tmp_path / "log_backend.py"
    module.write_text("""\
import llm
class Backend(llm.Model):
    model_id = "worker-fake"
    supports_tools = True
    def execute(self, prompt, stream, response, conversation):
        yield "worker result"
class Model:
    def __new__(cls, **kwargs):
        from workshop.agent.models import LlmModel
        from unittest.mock import patch
        with patch("workshop.agent.models.llm.get_model",
                   return_value=Backend()):
            return LlmModel(**kwargs)
""")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.getcwd())
    path = tmp_path / "logs.db"
    config = {
        "model": {"model_class": "log_backend.Model", "protocol": "native"},
        "workshop": {
            "llm": {"logging": {"enabled": True, "database": str(path)}}
        },
    }
    result = SupervisedAgent(config).run("test task")
    assert result["submission"] == "worker result"
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM turns").fetchone()[0] == 1


def test_insecure_existing_database_is_rejected(tmp_path, monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX permissions")
    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend()
    )
    path = tmp_path / "logs.db"
    path.touch(mode=0o644)
    path.chmod(0o644)
    model = LlmModel(protocol="native", retry_attempts=1)
    model.configure_log_database(path)
    with pytest.raises(PermissionError, match="private"):
        model.query([{"role": "user", "content": "hi"}])


def test_logging_failure_does_not_retry_model(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model", lambda _: Backend()
    )
    model = LlmModel(protocol="native", retry_attempts=3)
    model.configure_log_database(tmp_path / "logs.db")
    monkeypatch.setattr(
        Response,
        "log_to_db",
        lambda self, db: (_ for _ in ()).throw(RuntimeError("log failed")),
    )
    with pytest.raises(RuntimeError, match="log failed"):
        model.query([{"role": "user", "content": "hi"}])
    assert len(model._conversation.responses) == 1
