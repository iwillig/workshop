"""An agent that displays model responses and command observations."""

import threading
from dataclasses import dataclass

import click

from workshop.agent.default_agent import AgentConfig, DefaultAgent
from workshop.agent.exceptions import FormatError, UserInterruption


@dataclass
class InteractiveAgentConfig(AgentConfig):
    mode: str = "yolo"
    """Legacy setting: only unattended execution is supported."""


class InteractiveAgent(DefaultAgent):
    def __init__(
        self,
        model,
        env,
        *,
        config_class: type = InteractiveAgentConfig,
        **kwargs,
    ):
        super().__init__(model, env, config_class=config_class, **kwargs)
        self._displayed_actions = 0
        self._progress_omitted = False
        self._reset_usage()
        self.progress_sink = None
        self.stop_event = None
        self.tool_call_count = 0
        self._tool_count_lock = threading.Lock()
        if self.config.mode != "yolo":
            raise ValueError(
                "Tool approval is no longer supported; remove agent.mode "
                "or set it to 'yolo'. "
                "Commands will run without confirmation."
            )

    def _emit(self, text, *, color=None):
        if self.progress_sink is not None:
            self.progress_sink(text)
        elif color:
            click.secho(text, fg=color)
        else:
            click.echo(text)

    def _check_stopped(self):
        if self.stop_event is not None and self.stop_event.is_set():
            raise UserInterruption(
                {
                    "role": "exit",
                    "content": "Stopped by user",
                    "extra": {
                        "exit_status": "UserInterruption",
                        "submission": "",
                    },
                }
            )

    def _reset_usage(self):
        self._usage_totals = {"input": 0, "output": 0}
        self._usage_seen = {"input": False, "output": False}
        self._usage_missing = {"input": False, "output": False}
        self._usage_lines = 0
        self._usage_omitted = False
        self._has_usage = False

    def _show_usage(self, extra):
        if "usage" not in extra:
            return
        self._has_usage = True
        usage = extra.get("usage") or {}
        current = {}
        for key in ("input", "output"):
            value = usage.get(key)
            if type(value) is int and value >= 0:
                self._usage_totals[key] += value
                self._usage_seen[key] = True
                current[key] = f"{value:,}"
            else:
                self._usage_missing[key] = True
                current[key] = "unknown"
        if self.progress_sink is not None or self._usage_lines < 30:
            self._emit(
                f"[tokens] call: input {current['input']}, "
                f"output {current['output']} | total: "
                f"input {self._usage_total('input')}, "
                f"output {self._usage_total('output')}"
            )
            self._usage_lines += 1
        elif not self._usage_omitted:
            self._emit("[Further token progress omitted]")
            self._usage_omitted = True

    def _usage_total(self, key):
        if not self._usage_seen[key]:
            return "unknown"
        suffix = " partial" if self._usage_missing[key] else ""
        return f"{self._usage_totals[key]:,}{suffix}"

    def on_action_start(self, action: dict) -> None:
        with self._tool_count_lock:
            self.tool_call_count += 1
            if self.progress_sink is not None:
                self._emit(f"[tools] calls: {self.tool_call_count}")

    def run(self, task: str = "", **kwargs) -> dict:
        self.tool_call_count = 0
        self._displayed_actions = 0
        self._progress_omitted = False
        self._reset_usage()
        try:
            return super().run(task, **kwargs)
        finally:
            self._emit(f"[tools] calls: {self.tool_call_count}")
            if self._has_usage:
                self._emit(
                    f"[tokens] run total: input {self._usage_total('input')}, "
                    f"output {self._usage_total('output')}"
                )

    def query(self) -> dict:
        self._check_stopped()
        if self.progress_sink is not None:
            self._emit("Waiting for model response")
        has_stream_callback = self.progress_sink is not None and hasattr(
            self.model, "stream_callback"
        )
        previous_callback = getattr(self.model, "stream_callback", None)
        if has_stream_callback:
            self.model.stream_callback = lambda source, text: (
                None
                if source == "reset"
                else self._emit(f"[model:{source}] {text}")
            )
        try:
            message = super().query()
        except FormatError as exc:
            if exc.messages:
                self._show_usage(exc.messages[0].get("extra", {}))
            raise
        finally:
            if has_stream_callback:
                self.model.stream_callback = previous_callback
        self._show_usage(message.get("extra", {}))
        self._check_stopped()
        for action in message.get("extra", {}).get("actions", []):
            if self.progress_sink is None and self._displayed_actions >= 30:
                if not self._progress_omitted:
                    self._emit("[Further tool progress omitted]")
                    self._progress_omitted = True
                continue
            tool = str(action.get("tool", "bash")).replace("\n", " ")[:60]
            args = action.get("arguments", {})
            path = args.get("path") if isinstance(args, dict) else None
            detail = (
                f" {str(path).replace(chr(10), ' ')[:120]}" if path else ""
            )
            self._emit(f"[tool] {tool}{detail}", color="cyan")
            self._displayed_actions += 1
        return message

    def execute_actions(self, message: dict) -> list[dict]:
        self._check_stopped()
        return super().execute_actions(message)
