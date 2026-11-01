import subprocess
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from workshop.agent.cli import agent_commands
from workshop.agent.environments import DockerEnvironment


@pytest.mark.parametrize(
    "status,expected",
    [("Submitted", 0), ("LimitsExceeded", 1), ("TimeExceeded", 1)],
)
def test_cli_exit_status(monkeypatch, status, expected):
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent",
        lambda config: SimpleNamespace(
            run=lambda task: {"exit_status": status}
        ),
    )
    result = CliRunner().invoke(agent_commands, ["run", "--task", "task"])
    assert result.exit_code == expected
    assert status in result.output


def test_docker_cleanup_waits_and_is_idempotent(monkeypatch):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1] == "run":
            return subprocess.CompletedProcess(cmd, 0, stdout="container-id\n")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr("workshop.agent.environments.subprocess.run", run)
    env = DockerEnvironment(image="test")
    env.ensure_started()
    env.cleanup()
    env.cleanup()
    assert calls[1] == ["docker", "stop", "container-id"]
    assert len(calls) == 2


def test_local_command_output_is_bounded_during_capture():
    import sys
    from workshop.agent.environments import LocalEnvironment

    command = f"{sys.executable} -c \"print('x' * 200000)\""
    result = LocalEnvironment().execute({"command": command})
    assert result["returncode"] == 0
    assert len(result["output"]) < 50100
    assert "[output truncated]" in result["output"]


def test_large_tool_output_is_bounded_before_model():
    from workshop.agent.default_agent import DefaultAgent

    class Model:
        def get_template_vars(self):
            return {}

        def format_observation_messages(self, message, outputs, template_vars):
            return [{"role": "user", "content": outputs[0]["output"]}]

    class Environment:
        def get_template_vars(self):
            return {}

        def execute(self, action):
            return {
                "output": "x" * 100000,
                "returncode": 0,
                "exception_info": "",
            }

    agent = DefaultAgent(Model(), Environment())
    result = agent.execute_actions(
        {"extra": {"actions": [{"command": "test"}]}}
    )
    assert len(result[0]["content"]) < 51000
    assert "truncated" in result[0]["content"]


@pytest.mark.parametrize("attempts", [0, -1])
def test_retry_attempts_must_be_positive(attempts):
    from workshop.agent.models import LlmModel

    with pytest.raises(ValueError, match="retry_attempts"):
        LlmModel(retry_attempts=attempts)


def test_cleanup_failure_does_not_mask_primary_error(caplog):
    from workshop.agent.default_agent import DefaultAgent

    class Environment:
        def cleanup(self):
            raise RuntimeError("cleanup failed")

    agent = DefaultAgent(None, Environment())
    agent._run = lambda task, **kwargs: (_ for _ in ()).throw(
        ValueError("primary")
    )
    with pytest.raises(ValueError, match="primary") as error:
        agent.run("task")
    assert "cleanup failed" in error.value.__notes__[0]
    assert "cleanup failed" in caplog.text


def test_cleanup_failure_preserves_result_and_reports_warning(caplog):
    from workshop.agent.default_agent import DefaultAgent

    class Environment:
        def cleanup(self):
            raise RuntimeError("cleanup failed")

    agent = DefaultAgent(None, Environment())
    agent._run = lambda task, **kwargs: {
        "exit_status": "Submitted",
        "submission": "done",
    }
    result = agent.run("task")
    assert result["submission"] == "done"
    assert "cleanup failed" in result["cleanup_warning"]
    assert "cleanup failed" in caplog.text


def test_agent_cleans_environment_even_on_failure():
    from workshop.agent.default_agent import DefaultAgent

    class Model:
        def format_message(self, **kwargs):
            return kwargs

        def get_template_vars(self):
            return {}

        def query(self, messages):
            raise RuntimeError("failed")

        def serialize(self):
            return {}

    class Environment:
        def __init__(self):
            self.cleaned = False

        def get_template_vars(self):
            return {}

        def serialize(self):
            return {}

        def cleanup(self):
            self.cleaned = True

    env = Environment()
    agent = DefaultAgent(
        Model(), env, system_template="sys", instance_template="task"
    )
    with pytest.raises(RuntimeError, match="failed"):
        agent.run("task")
    assert env.cleaned
