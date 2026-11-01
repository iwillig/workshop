import asyncio
import threading

from textual.widgets import Static

from workshop.agent.live_view import AgentLiveView


def test_live_view_updates_while_agent_is_blocked():
    started = threading.Event()
    release = threading.Event()

    class Agent:
        progress_sink = None
        stop_event = None

        def run(self, task):
            self.progress_sink("Waiting for model")
            started.set()
            release.wait(timeout=5)
            self.progress_sink("[tokens] call: input 10, output 2")
            return {"exit_status": "Submitted", "submission": "done"}

    async def run():
        app = AgentLiveView(Agent(), "task")
        async with app.run_test() as pilot:
            for _ in range(30):
                if started.is_set():
                    break
                await pilot.pause(0.05)
            assert started.is_set()
            await pilot.pause(0.1)
            assert "Waiting for model" in str(
                app.query_one("#activity", Static).content
            )
            release.set()
            for _ in range(50):
                if app.return_value is not None:
                    break
                await pilot.pause(0.05)
            assert app.return_value["result"]["submission"] == "done"

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_recent_tool_calls_remain_visible_while_waiting():
    started = threading.Event()
    release = threading.Event()

    class Agent:
        def run(self, task):
            for i in range(12):
                self.progress_sink(f"[tool] read file{i}.py")
            self.progress_sink("Waiting for model response")
            started.set()
            release.wait(timeout=5)
            return {"exit_status": "Submitted", "submission": "done"}

    async def run():
        app = AgentLiveView(Agent(), "task")
        async with app.run_test() as pilot:
            for _ in range(30):
                if started.is_set():
                    break
                await pilot.pause(0.05)
            await pilot.pause(0.1)
            history = str(app.query_one("#tools", Static).content)
            assert "file11.py" in history
            assert "file4.py" in history
            assert "file3.py" not in history
            assert "Waiting for model" in str(
                app.query_one("#activity", Static).content
            )
            release.set()
            for _ in range(50):
                if app.return_value is not None:
                    break
                await pilot.pause(0.05)
            assert app.return_value["tool_history"][-1] == "[tool] read file11.py"

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_live_sink_continues_receiving_tool_events_after_plain_limit(monkeypatch):
    from workshop.agent.default_agent import DefaultAgent
    from workshop.agent.interactive import InteractiveAgent

    monkeypatch.setattr(
        DefaultAgent,
        "query",
        lambda self: {
            "extra": {
                "actions": [
                    {"tool": "read", "arguments": {"path": str(i)}} for i in range(40)
                ]
            }
        },
    )
    events = []
    agent = InteractiveAgent(None, None)
    agent.progress_sink = events.append
    agent.query()
    assert "[tool] read 39" in events
    assert not any("omitted" in event for event in events)


def test_live_view_exits_with_worker_exception():
    class Agent:
        def run(self, task):
            raise RuntimeError("model failed")

    async def run():
        app = AgentLiveView(Agent(), "task")
        async with app.run_test() as pilot:
            for _ in range(50):
                if app.return_value is not None:
                    break
                await pilot.pause(0.05)
            assert str(app.return_value["error"]) == "model failed"

    asyncio.run(run())


def test_interactive_agent_emits_waiting_before_blocking_call(monkeypatch):
    from workshop.agent.default_agent import DefaultAgent
    from workshop.agent.interactive import InteractiveAgent

    events = []

    def query(self):
        assert events == ["Waiting for model response"]
        return {"extra": {"usage": {"input": 10, "output": 2}, "actions": []}}

    monkeypatch.setattr(DefaultAgent, "query", query)
    agent = InteractiveAgent(None, None)
    agent.progress_sink = events.append
    agent.query()
    assert "input 10" in events[1]


def test_cancel_after_model_response_prevents_tool_execution(monkeypatch):
    from workshop.agent.default_agent import DefaultAgent
    from workshop.agent.interactive import InteractiveAgent
    from workshop.agent.exceptions import UserInterruption
    import pytest

    stop = threading.Event()

    def query(self):
        stop.set()
        return {"extra": {"actions": [{"tool": "bash"}]}}

    monkeypatch.setattr(DefaultAgent, "query", query)
    agent = InteractiveAgent(None, None)
    agent.stop_event = stop
    with pytest.raises(UserInterruption):
        agent.query()


def test_cli_uses_live_view_on_tty(monkeypatch):
    from types import SimpleNamespace
    from click.testing import CliRunner
    from workshop.agent.cli import agent_commands
    from workshop.agent.interactive import InteractiveAgent
    from workshop.agent.live_view import AgentLiveView

    monkeypatch.setattr(
        "workshop.agent.cli.sys",
        SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: True),
            stdout=SimpleNamespace(isatty=lambda: True),
        ),
    )
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent", lambda config: InteractiveAgent(None, None)
    )

    def fake_run(self, **kwargs):
        self.latest_usage = "[tokens] run total: input 10, output 2"
        self.latest_thinking = "[model:reasoning] reviewing"
        return {
            "result": {"exit_status": "Submitted", "submission": "ok"},
            "tool_history": ["[tool] read a.py"],
            "model_snippet": "[model:reasoning] reviewing",
        }

    monkeypatch.setattr(AgentLiveView, "run", fake_run)
    result = CliRunner().invoke(agent_commands, ["run", "--task", "test"])
    assert result.exit_code == 0, result.output
    assert "ok" in result.output
    assert "[tool] read a.py" in result.output
    assert "[model:reasoning] reviewing" in result.output


def test_cli_returns_standard_interrupt_exit_code(monkeypatch):
    from types import SimpleNamespace
    from click.testing import CliRunner
    from workshop.agent.cli import agent_commands
    from workshop.agent.interactive import InteractiveAgent
    from workshop.agent.live_view import AgentLiveView

    monkeypatch.setattr(
        "workshop.agent.cli.sys",
        SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: True),
            stdout=SimpleNamespace(isatty=lambda: True),
        ),
    )
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent", lambda config: InteractiveAgent(None, None)
    )
    monkeypatch.setattr(
        AgentLiveView,
        "run",
        lambda self, **kwargs: {
            "result": {"exit_status": "UserInterruption", "submission": ""}
        },
    )
    result = CliRunner().invoke(agent_commands, ["run", "--task", "test"])
    assert result.exit_code == 130
    assert "incomplete" in result.output


def test_ctrl_c_waits_for_worker_to_finish():
    started = threading.Event()
    release = threading.Event()

    class Agent:
        def run(self, task):
            started.set()
            release.wait(timeout=5)
            return {"exit_status": "UserInterruption", "submission": ""}

    async def run():
        app = AgentLiveView(Agent(), "task")
        async with app.run_test() as pilot:
            for _ in range(30):
                if started.is_set():
                    break
                await pilot.pause(0.05)
            assert started.is_set()
            await pilot.press("ctrl+c")
            assert app.stop_event.is_set()
            assert app.return_value is None
            release.set()
            for _ in range(50):
                if app.return_value is not None:
                    break
                await pilot.pause(0.05)
            assert app.return_value["result"]["exit_status"] == "UserInterruption"

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_live_view_stop_requests_cancellation():
    agent = type("Agent", (), {"stop_event": None})()
    app = AgentLiveView(agent, "task")
    app.action_request_stop()
    assert agent.stop_event.is_set()
