"""The agent control loop, ported from mini-swe-agent's DefaultAgent.

See https://mini-swe-agent.com/latest/advanced/control_flow/ for a visual
explanation of the loop this file implements.
"""

import json
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import StrictUndefined, Template

from workshop.agent.builtin_tools import BuiltinTools
from workshop.agent.exceptions import (
    FormatError,
    InterruptAgentFlow,
    LimitsExceeded,
    Submitted,
    TimeExceeded,
)
from workshop.agent.prompts import (
    DEFAULT_INSTANCE_TEMPLATE,
    DEFAULT_SYSTEM_TEMPLATE,
)
from workshop.agent.serialize import config_as_dict, recursive_merge

TRAJECTORY_FORMAT = (
    "mini-swe-agent-1.1"  # compatible with mini-swe-agent's inspector
)


@dataclass
class AgentConfig:
    system_template: str = DEFAULT_SYSTEM_TEMPLATE
    """Template for the system message (the first message)."""
    instance_template: str = DEFAULT_INSTANCE_TEMPLATE
    """Template for the first user message specifying the task."""
    step_limit: int = 0
    """Maximum number of model calls. 0 means no limit."""
    cost_limit: float = 3.0
    """Stop after this cost; requires configured model token prices."""
    wall_time_limit_seconds: int = 0
    """Stop after this many seconds of wall-clock time. 0 means no limit."""
    max_consecutive_format_errors: int = 3
    """Exit after this many format errors in a row (0 = no limit)."""
    output_path: Path | None = None
    """Save the trajectory to this path."""
    parallel_tools: list[str] = field(default_factory=list)
    """Tools allowed to run concurrently; others are serial barriers."""
    max_parallel_tools: int = 4
    """Maximum number of concurrent tool calls."""


class DefaultAgent:
    def __init__(
        self, model, env, *, config_class: type = AgentConfig, **kwargs
    ):
        """See AgentConfig for permitted keyword arguments."""
        self.config = config_class(**kwargs)
        if self.config.max_parallel_tools < 1:
            raise ValueError("max_parallel_tools must be at least 1")
        self.messages: list[dict] = []
        self.model = model
        self.env = env
        self.extra_template_vars: dict = {}
        self.logger = logging.getLogger("workshop.agent")
        self.cost = 0.0
        self.n_calls = 0
        self.n_consecutive_format_errors = 0
        self._start_time = time.time()
        self.mcp_runtime = None
        self.builtin_tools = BuiltinTools(env)
        self.tool_providers = []

    def get_template_vars(self, **kwargs) -> dict:
        return recursive_merge(
            config_as_dict(self.config),
            self.env.get_template_vars(),
            self.model.get_template_vars(),
            {
                "n_model_calls": self.n_calls,
                "model_cost": self.cost,
                "elapsed_seconds": int(time.time() - self._start_time),
            },
            self.extra_template_vars,
            kwargs,
        )

    def _render_template(self, template: str) -> str:
        return Template(template, undefined=StrictUndefined).render(
            **self.get_template_vars()
        )

    def add_messages(self, *messages: dict) -> list[dict]:
        self.logger.debug(messages)
        self.messages.extend(messages)
        return list(messages)

    def handle_uncaught_exception(self, e: Exception) -> list[dict]:
        return self.add_messages(
            self.model.format_message(
                role="exit",
                content=str(e),
                extra={
                    "exit_status": type(e).__name__,
                    "submission": "",
                    "exception_str": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
        )

    def run(self, task: str = "", **kwargs) -> dict:
        """Run until the agent finishes, closing MCP sessions afterward."""
        result = None
        primary_error = None
        try:
            for provider in self.tool_providers:
                if start_run := getattr(provider, "start_run", None):
                    start_run()
            if start := getattr(self.env, "ensure_started", None):
                start()
            with self.mcp_runtime or nullcontext() as runtime:
                if (
                    getattr(
                        getattr(self.model, "config", None), "protocol", None
                    )
                    == "native"
                ):
                    self.model.native_tools = (
                        self.builtin_tools.tools
                        + [
                            tool
                            for provider in self.tool_providers
                            for tool in provider.tools
                        ]
                        + (runtime.tools if runtime else [])
                    )
                result = self._run(task, **kwargs)
                for provider in self.tool_providers:
                    if finish_run := getattr(provider, "finish_run", None):
                        result["git_review"] = {
                            "refs": finish_run(),
                            "context": provider.review.context(),
                            "coverage": provider.coverage_summary(),
                        }
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            if cleanup := getattr(self.env, "cleanup", None):
                try:
                    cleanup()
                except Exception as exc:
                    warning = f"Environment cleanup failed: {exc}"
                    self.logger.warning(warning)
                    if primary_error is not None:
                        primary_error.add_note(warning)
                    elif result is not None:
                        result["cleanup_warning"] = warning
        return result

    def _run(self, task: str = "", **kwargs) -> dict:
        self.extra_template_vars = {"task": task, **kwargs}
        self.messages = []
        self.cost = 0.0
        self.n_calls = 0
        self.n_consecutive_format_errors = 0
        self._start_time = time.time()
        if reset := getattr(self.model, "reset", None):
            reset()
        self.add_messages(
            self.model.format_message(
                role="system",
                content=self._render_template(self.config.system_template),
            ),
            self.model.format_message(
                role="user",
                content=self._render_template(self.config.instance_template),
            ),
        )
        while True:
            try:
                self.step()
                self.n_consecutive_format_errors = 0
            except FormatError as e:
                # Parsing failed after billing, before recording the cost.
                error_extra = e.messages[0].get("extra", {})
                self.cost += error_extra.get("cost", 0.0)
                if "response" in error_extra:
                    self.add_messages(
                        {
                            "role": "assistant",
                            "content": error_extra["response"],
                        }
                    )
                self.n_consecutive_format_errors += 1
                if (
                    0
                    < self.config.max_consecutive_format_errors
                    <= self.n_consecutive_format_errors
                ):
                    self.add_messages(
                        *e.messages,
                        {
                            "role": "exit",
                            "content": "RepeatedFormatError",
                            "extra": {
                                "exit_status": "RepeatedFormatError",
                                "submission": "",
                            },
                        },
                    )
                else:
                    self.add_messages(*e.messages)
            except InterruptAgentFlow as e:
                self.add_messages(*e.messages)
            except Exception as e:
                self.handle_uncaught_exception(e)
                raise
            finally:
                self.save(self.config.output_path)
            if self.messages[-1].get("role") == "exit":
                break
        return self.messages[-1].get("extra", {})

    def step(self) -> list[dict]:
        """Query the LM, execute actions."""
        return self.execute_actions(self.query())

    def query(self) -> dict:
        """Query the model and return its message. Override to add hooks."""
        if (
            0 < self.config.step_limit <= self.n_calls
            or 0 < self.config.cost_limit <= self.cost
        ):
            raise LimitsExceeded(
                {
                    "role": "exit",
                    "content": "LimitsExceeded",
                    "extra": {
                        "exit_status": "LimitsExceeded",
                        "submission": "",
                    },
                }
            )
        if (
            0
            < self.config.wall_time_limit_seconds
            <= int(time.time() - self._start_time)
        ):
            raise TimeExceeded(
                {
                    "role": "exit",
                    "content": "TimeExceeded",
                    "extra": {"exit_status": "TimeExceeded", "submission": ""},
                }
            )
        self.n_calls += 1
        message = self.model.query(self.messages)
        self.cost += message.get("extra", {}).get("cost", 0.0)
        self.add_messages(message)
        return message

    def on_action_start(self, action: dict) -> None:
        """Hook called when an action begins execution."""

    def execute_actions(self, message: dict) -> list[dict]:
        """Execute actions and return the added observation messages."""
        if message.get("extra", {}).get("native_final"):
            submission = message.get("content", "")
            raise Submitted(
                {
                    "role": "exit",
                    "content": submission,
                    "extra": {
                        "exit_status": "Submitted",
                        "submission": submission,
                    },
                }
            )
        actions = message.get("extra", {}).get("actions", [])
        outputs = []
        parallel_batch = []

        def execute(action):
            self.on_action_start(action)
            if (
                "tool" in action
                and getattr(
                    getattr(self.model, "config", None), "protocol", None
                )
                == "native"
            ):
                if action["tool"] in {
                    tool.name for tool in self.builtin_tools.tools
                }:
                    return self.builtin_tools.execute(action)
                for provider in self.tool_providers:
                    if action["tool"] in {
                        tool.name for tool in provider.tools
                    }:
                        return provider.execute(action)
                if self.mcp_runtime:
                    return self.mcp_runtime.execute(action)
                return {
                    "output": f"Unknown tool: {action['tool']}",
                    "returncode": 1,
                    "exception_info": "",
                }
            return self.env.execute(action)

        def flush():
            if parallel_batch:
                with ThreadPoolExecutor(
                    max_workers=self.config.max_parallel_tools
                ) as pool:
                    outputs.extend(pool.map(execute, parallel_batch))
                parallel_batch.clear()

        for action in actions:
            if action.get("tool") in self.config.parallel_tools:
                parallel_batch.append(action)
            else:
                flush()
                outputs.append(execute(action))
        flush()
        for output in outputs:
            text = output.get("output", "")
            if len(text) > 50000:
                output["output"] = (
                    text[:25000] + "\n[output truncated]\n" + text[-25000:]
                )
        return self.add_messages(
            *self.model.format_observation_messages(
                message, outputs, self.get_template_vars()
            )
        )

    def serialize(self, *extra_dicts) -> dict:
        """Serialize agent state as a JSON-compatible dictionary."""
        last_message = self.messages[-1] if self.messages else {}
        last_extra = last_message.get("extra", {})
        agent_data = {
            "info": {
                "model_stats": {
                    "instance_cost": self.cost,
                    "api_calls": self.n_calls,
                },
                "config": {
                    "agent": config_as_dict(self.config),
                    "agent_type": (
                        f"{self.__class__.__module__}."
                        f"{self.__class__.__name__}"
                    ),
                },
                "exit_status": last_extra.get("exit_status", ""),
                "submission": last_extra.get("submission", ""),
            },
            "messages": self.messages,
            "trajectory_format": TRAJECTORY_FORMAT,
        }
        return recursive_merge(
            agent_data,
            self.model.serialize(),
            self.env.serialize(),
            *extra_dicts,
        )

    def save(self, path: Path | None, *extra_dicts) -> dict:
        """Save the trajectory if a path is given; return serialized data."""
        data = self.serialize(*extra_dicts)
        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, default=repr))
        return data
