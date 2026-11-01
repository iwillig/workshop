import json
import threading

import pytest

from workshop.agent.default_agent import DefaultAgent
from workshop.agent.environments import LocalEnvironment
from workshop.agent.exceptions import FormatError, Submitted
from workshop.agent.interactive import InteractiveAgent
from workshop.agent.models import (
    DEFAULT_ACTION_REGEX,
    extract_prompt,
    format_observation_messages,
    parse_regex_actions,
)
from workshop.agent.prompts import (
    DEFAULT_FORMAT_ERROR_TEMPLATE,
    DEFAULT_OBSERVATION_TEMPLATE,
)


class ScriptedModel:
    """Replay scripted responses through the real parsing path."""

    def __init__(self, *responses: str):
        self.responses = list(responses)

    def query(self, messages, **kwargs):
        content = self.responses.pop(0)
        actions = parse_regex_actions(
            content,
            action_regex=DEFAULT_ACTION_REGEX,
            format_error_template=DEFAULT_FORMAT_ERROR_TEMPLATE,
        )
        return {
            "role": "assistant",
            "content": content,
            "extra": {"actions": actions, "cost": 0.0},
        }

    def format_message(self, **kwargs):
        return dict(kwargs)

    def format_observation_messages(
        self, message, outputs, template_vars=None
    ):
        return format_observation_messages(
            outputs,
            observation_template=DEFAULT_OBSERVATION_TEMPLATE,
            template_vars=template_vars,
        )

    def get_template_vars(self, **kwargs):
        return {}

    def serialize(self):
        return {}


def response(command: str) -> str:
    return f"THOUGHT: run it\n\n```mswea_bash_command\n{command}\n```"


def test_parse_regex_actions_single_action():
    actions = parse_regex_actions(
        response("echo hi"),
        action_regex=DEFAULT_ACTION_REGEX,
        format_error_template="{{error}}",
    )
    assert actions == [{"command": "echo hi"}]


@pytest.mark.parametrize(
    "content", ["no action here", response("a") + "\n" + response("b")]
)
def test_parse_regex_actions_rejects_wrong_count(content):
    with pytest.raises(FormatError) as excinfo:
        parse_regex_actions(
            content,
            action_regex=DEFAULT_ACTION_REGEX,
            format_error_template="{{error}}",
        )
    assert excinfo.value.messages[0]["role"] == "user"


def test_extract_prompt_first_and_followup_calls():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "task"},
    ]
    assert extract_prompt(messages, 0) == ("sys", "task")
    messages += [
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "obs1"},
        {"role": "user", "content": "obs2"},
    ]
    assert extract_prompt(messages, 1) == (None, "obs1\n\nobs2")


def test_extract_prompt_detects_state_mismatch():
    messages = [
        {"role": "user", "content": "task"},
        {"role": "assistant", "content": "r"},
    ]
    with pytest.raises(RuntimeError):
        extract_prompt(messages, 0)


def test_local_environment_executes_commands():
    env = LocalEnvironment(timeout=5)
    output = env.execute({"command": "echo hello"})
    assert output["returncode"] == 0
    assert "hello" in output["output"]


def test_local_environment_timeout_is_an_observation():
    env = LocalEnvironment(timeout=1)
    output = env.execute({"command": "sleep 5"})
    assert output["returncode"] == -1
    assert "error occurred" in output["exception_info"]


def test_local_environment_submit_sentinel():
    env = LocalEnvironment(timeout=5)
    with pytest.raises(Submitted) as excinfo:
        env.execute(
            {
                "command": (
                    "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && echo done"
                )
            }
        )
    assert excinfo.value.messages[0]["extra"]["submission"] == "done\n"


def test_agent_runs_to_submission(tmp_path):
    trajectory_path = tmp_path / "run.traj.json"
    model = ScriptedModel(
        response("echo hello"),
        response(
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && echo all done"
        ),
    )
    agent = DefaultAgent(
        model, LocalEnvironment(timeout=5), output_path=trajectory_path
    )
    result = agent.run("say hello")
    assert result["exit_status"] == "Submitted"
    assert result["submission"] == "all done\n"
    data = json.loads(trajectory_path.read_text())
    assert data["info"]["exit_status"] == "Submitted"
    roles = [m["role"] for m in data["messages"]]
    assert roles == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "exit",
    ]


def test_interactive_agent_runs_without_prompt(monkeypatch):
    def unexpected_prompt(*args, **kwargs):
        raise AssertionError("agent must not prompt for approval")

    monkeypatch.setattr("click.prompt", unexpected_prompt)
    model = ScriptedModel(
        response("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT")
    )
    result = InteractiveAgent(model, LocalEnvironment(timeout=5)).run("finish")
    assert result["exit_status"] == "Submitted"


def test_reused_agent_has_fresh_run_limits():
    model = ScriptedModel(
        response("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"),
        response("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"),
    )
    agent = DefaultAgent(model, LocalEnvironment(timeout=5), step_limit=1)
    assert agent.run("first")["exit_status"] == "Submitted"
    assert agent.run("second")["exit_status"] == "Submitted"
    assert agent.n_calls == 1


def test_parallel_tools_overlap_and_serial_action_is_barrier():
    barrier = threading.Barrier(2, timeout=2)
    completed = []

    class Environment:
        def execute(self, action):
            name = action["name"]
            if name in ("first", "second"):
                barrier.wait()
            else:
                assert set(completed) == {"first", "second"}
            completed.append(name)
            return {"output": name, "returncode": 0, "exception_info": ""}

        def get_template_vars(self):
            return {}

    model = ScriptedModel()
    agent = DefaultAgent(model, Environment(), parallel_tools=["read"])
    message = {
        "extra": {
            "actions": [
                {"tool": "read", "name": "first"},
                {"tool": "read", "name": "second"},
                {"tool": "edit", "name": "third"},
            ]
        }
    }
    observations = agent.execute_actions(message)
    assert [item["extra"]["raw_output"] for item in observations] == [
        "first",
        "second",
        "third",
    ]


def test_tools_are_serial_by_default():
    seen = []

    class Environment:
        def execute(self, action):
            seen.append(action["name"])
            return {
                "output": action["name"],
                "returncode": 0,
                "exception_info": "",
            }

        def get_template_vars(self):
            return {}

    agent = DefaultAgent(ScriptedModel(), Environment())
    agent.execute_actions(
        {
            "extra": {
                "actions": [
                    {"tool": "read", "name": "first"},
                    {"tool": "read", "name": "second"},
                ]
            }
        }
    )
    assert seen == ["first", "second"]


def test_agent_step_limit(tmp_path):
    model = ScriptedModel(response("echo one"), response("echo two"))
    agent = DefaultAgent(model, LocalEnvironment(timeout=5), step_limit=1)
    result = agent.run("loop forever")
    assert result["exit_status"] == "LimitsExceeded"


def test_agent_recovers_from_format_error():
    model = ScriptedModel(
        "I forgot the code block.",
        response("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && echo fixed"),
    )
    agent = DefaultAgent(model, LocalEnvironment(timeout=5))
    result = agent.run("recover")
    assert result["exit_status"] == "Submitted"
    format_errors = [
        m
        for m in agent.messages
        if m.get("extra", {}).get("interrupt_type") == "FormatError"
    ]
    assert len(format_errors) == 1


def test_agent_exits_after_repeated_format_errors():
    model = ScriptedModel("bad", "still bad")
    agent = DefaultAgent(
        model, LocalEnvironment(timeout=5), max_consecutive_format_errors=2
    )
    result = agent.run("never valid")
    assert result["exit_status"] == "RepeatedFormatError"
