from types import SimpleNamespace

from click.testing import CliRunner

from workshop.agent.cli import agent_commands
from workshop.agent.interactive import InteractiveAgent
from workshop.agent.default_agent import DefaultAgent


def test_long_submission_is_bounded_and_marks_omission(monkeypatch):
    text = "start\n" + "x" * 20000 + "\nend"
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent",
        lambda config: SimpleNamespace(
            run=lambda task: {"exit_status": "Submitted", "submission": text}
        ),
    )
    result = CliRunner().invoke(agent_commands, ["run", "--task", "task"])
    assert result.exit_code == 0
    assert "start" in result.output
    assert "truncated" in result.output.lower()
    assert len(result.output) < 5000
    assert "--output" in result.output


def test_short_submission_with_trailing_newline_is_not_marked_truncated(monkeypatch):
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent",
        lambda config: SimpleNamespace(
            run=lambda task: {"exit_status": "Submitted", "submission": "All clear.\n"}
        ),
    )
    result = CliRunner().invoke(agent_commands, ["run", "--task", "task"])
    assert result.exit_code == 0
    assert "All clear." in result.output
    assert "truncated" not in result.output.lower()


def test_progress_is_bounded(monkeypatch, capsys):
    message = {
        "extra": {
            "actions": [
                {"tool": "read", "arguments": {"path": f"file{i}.py"}}
                for i in range(100)
            ]
        }
    }
    monkeypatch.setattr(DefaultAgent, "query", lambda self: message)
    agent = InteractiveAgent(None, None)
    agent.query()
    output = capsys.readouterr().out
    assert len(output.splitlines()) <= 31
    assert "omitted" in output.lower()
