import pytest
from click.testing import CliRunner

from workshop.agent.cli import agent_commands
from workshop.agent.config import build_agent, load_config


def test_repository_review_example_uses_only_read_tool(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    monkeypatch.setattr(
        "workshop.agent.models.llm.get_model",
        lambda _: SimpleNamespace(conversation=lambda: object()),
    )
    path = Path(__file__).resolve().parents[1] / "examples" / "review-agent.yaml"
    agent = build_agent(load_config(path, agent_name="reviewer"))
    assert [tool.name for tool in agent.builtin_tools.tools] == ["read"]
    assert agent.mcp_runtime is None
    assert agent.model.config.protocol == "native"
    assert agent.model.config.model_name == "hf-glm"


def test_named_agent_selection_and_relative_prompt(tmp_path):
    (tmp_path / "system.txt").write_text("Named system")
    config_path = tmp_path / "agents.yaml"
    config_path.write_text("""\
agents:
  reviewer:
    model:
      protocol: native
    prompts:
      system_file: system.txt
    environment:
      cwd: /tmp
    limits:
      step_limit: 7
    tools:
      read: {}
  coder:
    agent:
      agent_class: default
    limits:
      step_limit: 3
""")
    config = load_config(config_path, agent_name="reviewer")
    agent = build_agent(config)
    assert agent.config.system_template == "Named system"
    assert agent.config.step_limit == 7
    assert [tool.name for tool in agent.builtin_tools.tools] == ["read"]
    assert load_config(config_path, agent_name="coder")["agent"]["step_limit"] == 3
    with pytest.raises(ValueError, match="Select"):
        load_config(config_path)
    with pytest.raises(ValueError, match="Unknown"):
        load_config(config_path, agent_name="missing")


def test_cli_selects_named_agent_and_applies_overrides(tmp_path, monkeypatch):
    path = tmp_path / "agents.yaml"
    path.write_text("agents:\n  first:\n    limits:\n      step_limit: 7\n")
    seen = {}

    class Agent:
        def run(self, task):
            return {"exit_status": "Submitted"}

    def build(config):
        seen.update(config)
        return Agent()

    monkeypatch.setattr("workshop.agent.cli.build_agent", build)
    result = CliRunner().invoke(
        agent_commands,
        [
            "run",
            "--config",
            str(path),
            "--agent",
            "first",
            "--step-limit",
            "2",
            "--task",
            "hi",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["agent"]["step_limit"] == 2


def test_named_agents_reject_unknown_keys_and_tools(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("agents:\n  first:\n    unexpected: true\n")
    with pytest.raises(ValueError, match="unexpected"):
        load_config(path, agent_name="first")
    path.write_text(
        "agents:\n  first:\n    model:\n      protocol: native\n    tools:\n      unknown: {}\n"
    )
    with pytest.raises(ValueError, match="unknown"):
        build_agent(load_config(path, agent_name="first"))
