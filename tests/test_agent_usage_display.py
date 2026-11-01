from workshop.agent.default_agent import DefaultAgent
from workshop.agent.interactive import InteractiveAgent


def test_usage_progress_reports_per_call_and_cumulative(monkeypatch, capsys):
    messages = iter(
        [
            {"extra": {"usage": {"input": 100, "output": 20}, "actions": []}},
            {"extra": {"usage": {"input": 50, "output": 5}, "actions": []}},
        ]
    )
    monkeypatch.setattr(DefaultAgent, "query", lambda self: next(messages))
    agent = InteractiveAgent(None, None)
    agent.query()
    agent.query()
    output = capsys.readouterr().out
    assert "100" in output and "20" in output
    assert "150" in output and "25" in output
    assert "input" in output.lower() and "output" in output.lower()


def test_usage_on_format_error_is_reported(monkeypatch, capsys):
    import pytest
    from workshop.agent.exceptions import FormatError

    def query(self):
        raise FormatError({"extra": {"usage": {"input": 9, "output": 2}}})

    monkeypatch.setattr(DefaultAgent, "query", query)
    agent = InteractiveAgent(None, None)
    with pytest.raises(FormatError):
        agent.query()
    assert "input 9" in capsys.readouterr().out


def test_missing_usage_is_not_reported_as_zero(monkeypatch, capsys):
    messages = iter(
        [
            {"extra": {"usage": {"input": 10, "output": 2}, "actions": []}},
            {"extra": {"usage": {}, "actions": []}},
        ]
    )
    monkeypatch.setattr(DefaultAgent, "query", lambda self: next(messages))
    agent = InteractiveAgent(None, None)
    agent.query()
    agent.query()
    output = capsys.readouterr().out.lower()
    assert "unknown" in output
    assert "partial" in output
