"""Inline Textual progress view for a foreground interactive agent."""

import threading
import time
from collections import deque

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.worker import Worker, WorkerState
from textual.widgets import Static


class Progress(Message):
    def __init__(self, text):
        super().__init__()
        self.text = text


class AgentLiveView(App):
    """Run a synchronous agent in a worker while the UI remains responsive."""

    CSS = """
    Screen { height: auto; }
    #activity { height: auto; }
    #tools { height: auto; }
    #tool-count { height: auto; }
    #thinking { height: auto; }
    #usage { height: auto; }
    #elapsed { height: 1; }
    """
    BINDINGS = [
        Binding("ctrl+c", "request_stop", "Stop", priority=True),
        Binding("ctrl+q", "request_stop", "Stop", priority=True),
    ]

    def __init__(self, agent, task):
        super().__init__()
        self.agent = agent
        self.agent_task = task
        self.stop_event = threading.Event()
        self.agent.stop_event = self.stop_event
        self.started = time.monotonic()
        self.latest = "Starting agent"
        self.latest_usage = "Tokens: waiting for provider"
        self.latest_thinking = "No model output yet"
        self.tool_history = deque(maxlen=8)
        self.latest_tool_count = "[tools] calls: 0"

    def compose(self) -> ComposeResult:
        yield Static("Starting agent", id="activity", markup=False)
        yield Static(self.latest_thinking, id="thinking", markup=False)
        yield Static("Recent tools: none yet", id="tools", markup=False)
        yield Static(self.latest_tool_count, id="tool-count", markup=False)
        yield Static(self.latest_usage, id="usage", markup=False)
        yield Static(
            "Elapsed: 0s | Ctrl+C: stop now",
            id="elapsed",
            markup=False,
        )

    def on_mount(self):
        self.set_interval(0.25, self._update_elapsed)
        self.run_worker(self._run_agent, thread=True, exit_on_error=False)

    def _run_agent(self):
        self.agent.progress_sink = lambda text: self.post_message(Progress(text))
        try:
            return {"result": self.agent.run(self.agent_task)}
        except Exception as exc:
            return {"error": exc}
        finally:
            self.agent.progress_sink = None
            self.agent.stop_event = None

    def on_progress(self, event: Progress):
        if event.text.startswith("[model:"):
            self.latest_thinking = event.text
            self.query_one("#thinking", Static).update(event.text)
        elif event.text.startswith("[tokens]"):
            self.latest_usage = event.text
            self.query_one("#usage", Static).update(event.text)
        elif event.text.startswith("[tools]"):
            self.latest_tool_count = event.text
            self.query_one("#tool-count", Static).update(event.text)
        elif event.text.startswith("[tool]"):
            self.tool_history.append(event.text)
            self.query_one("#tools", Static).update(
                "Recent tools:\n" + "\n".join(self.tool_history)
            )
        else:
            self.latest = event.text
            self.query_one("#activity", Static).update(event.text)

    def _update_elapsed(self):
        elapsed = int(time.monotonic() - self.started)
        state = "Stopping agent" if self.stop_event.is_set() else "Ctrl+C: stop now"
        self.query_one("#elapsed", Static).update(f"Elapsed: {elapsed}s | {state}")

    def action_request_stop(self):
        self.stop_event.set()
        if cancel := getattr(self.agent, "cancel", None):
            cancel()

    def on_worker_state_changed(self, event: Worker.StateChanged):
        if event.state == WorkerState.SUCCESS:
            outcome = event.worker.result
            outcome["tool_history"] = list(self.tool_history)
            outcome["tool_count"] = self.latest_tool_count
            if self.latest_thinking != "No model output yet":
                outcome["model_snippet"] = self.latest_thinking
            self.exit(outcome)
        elif event.state in {WorkerState.ERROR, WorkerState.CANCELLED}:
            self.exit(
                {"error": event.worker.error or RuntimeError("Agent worker stopped")}
            )
