import subprocess
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from workshop.agent.cli import agent_commands
from workshop.agent.environments import DockerEnvironment


@pytest.mark.parametrize(
    "status,expected", [("Submitted", 0), ("LimitsExceeded", 1), ("TimeExceeded", 1)]
)
def test_cli_exit_status(monkeypatch, status, expected):
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent",
        lambda config: SimpleNamespace(run=lambda task: {"exit_status": status}),
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
            return {"output": "x" * 100000, "returncode": 0, "exception_info": ""}

    agent = DefaultAgent(Model(), Environment())
    result = agent.execute_actions({"extra": {"actions": [{"command": "test"}]}})
    assert len(result[0]["content"]) < 51000
    assert "truncated" in result[0]["content"]


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
    agent = DefaultAgent(Model(), env, system_template="sys", instance_template="task")
    with pytest.raises(RuntimeError, match="failed"):
        agent.run("task")
    assert env.cleaned
