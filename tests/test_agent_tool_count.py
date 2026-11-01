import asyncio
import threading

from textual.widgets import Static

from workshop.agent.interactive import InteractiveAgent
from workshop.agent.live_view import AgentLiveView


def test_interactive_counts_executed_tool_calls(capsys):
    class Model:
        def get_template_vars(self):
            return {}

        def format_observation_messages(self, message, outputs, template_vars):
            return [{"role": "user", "content": output["output"]} for output in outputs]

    class Environment:
        def get_template_vars(self):
            return {}

        def execute(self, action):
            return {"output": "ok", "returncode": 0, "exception_info": ""}

    agent = InteractiveAgent(Model(), Environment())
    agent.execute_actions(
        {"extra": {"actions": [{"command": "one"}, {"command": "two"}]}}
    )
    assert agent.tool_call_count == 2


def test_parallel_calls_are_all_counted():
    class Model:
        def get_template_vars(self):
            return {}

        def format_observation_messages(self, message, outputs, template_vars):
            return []

    class Environment:
        def get_template_vars(self):
            return {}

        def execute(self, action):
            return {"output": "ok", "returncode": 0, "exception_info": ""}

    agent = InteractiveAgent(
        Model(), Environment(), parallel_tools=["read"], max_parallel_tools=8
    )
    agent.execute_actions(
        {"extra": {"actions": [{"tool": "read"} for _ in range(100)]}}
    )
    assert agent.tool_call_count == 100


def test_live_view_shows_latest_model_snippet_without_touching_tools():
    started = threading.Event()
    release = threading.Event()

    class Agent:
        def run(self, task):
            self.progress_sink("[tool] read a.py")
            self.progress_sink("[model:reasoning] Checking the parser")
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
            assert "Checking the parser" in str(
                app.query_one("#thinking", Static).content
            )
            assert "read a.py" in str(app.query_one("#tools", Static).content)
            assert "Waiting for model" in str(
                app.query_one("#activity", Static).content
            )
            release.set()
            for _ in range(50):
                if app.return_value is not None:
                    break
                await pilot.pause(0.05)
            assert app.return_value["model_snippet"].startswith("[model:reasoning]")

    try:
        asyncio.run(run())
    finally:
        release.set()


def test_live_view_displays_tool_count():
    started = threading.Event()
    release = threading.Event()

    class Agent:
        def run(self, task):
            self.progress_sink("[tools] calls: 3")
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
            assert "3" in str(app.query_one("#tool-count", Static).content)
            release.set()
            for _ in range(50):
                if app.return_value is not None:
                    break
                await pilot.pause(0.05)
            assert app.return_value["tool_count"] == "[tools] calls: 3"

    try:
        asyncio.run(run())
    finally:
        release.set()
