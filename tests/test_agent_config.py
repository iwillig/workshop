import pytest

from workshop.agent.config import (
    DEFAULT_CONFIG_PATH,
    build_agent,
    load_config,
    resolve_class,
)
from workshop.agent.default_agent import DefaultAgent
from workshop.agent.environments import LocalEnvironment
from workshop.agent.interactive import InteractiveAgent
from workshop.agent.models import LlmModel


def test_default_config_builds_interactive_agent():
    agent = build_agent(load_config(DEFAULT_CONFIG_PATH))
    assert isinstance(agent, InteractiveAgent)
    assert agent.config.step_limit == 50
    assert isinstance(agent.env, LocalEnvironment)
    assert agent.env.config.env["PAGER"] == "cat"
    assert isinstance(agent.model, LlmModel)


def test_obsolete_confirm_mode_is_rejected():
    with pytest.raises(ValueError, match="approval"):
        InteractiveAgent(None, None, mode="confirm")


def test_yaml_values_reach_dataclass_configs(tmp_path):
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(
        """
agent:
  agent_class: default
  step_limit: 7
  max_consecutive_format_errors: 2
environment:
  environment_class: local
  cwd: /tmp
  timeout: 5
model:
  model_class: llm
  model_options:
    temperature: 0
"""
    )
    agent = build_agent(load_config(config_path))
    assert type(agent) is DefaultAgent
    assert agent.config.step_limit == 7
    assert agent.config.max_consecutive_format_errors == 2
    assert agent.env.config.cwd == "/tmp"
    assert agent.env.config.timeout == 5
    assert agent.model.config.model_options == {"temperature": 0}


def test_build_agent_overrides_take_precedence():
    config = load_config(DEFAULT_CONFIG_PATH)
    agent = build_agent(config, step_limit=2)
    assert agent.config.step_limit == 2


def test_empty_sections_are_normalized(tmp_path):
    config_path = tmp_path / "sparse.yaml"
    config_path.write_text("agent:\n")
    config = load_config(config_path)
    assert config["agent"] == {}
    assert config["environment"] == {}
    agent = build_agent(config)
    assert isinstance(agent, InteractiveAgent)


def test_system_template_file_relative_to_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "system.txt").write_text(
        "System for {{ task }}", encoding="utf-8"
    )
    config_path = config_dir / "agent.yaml"
    config_path.write_text("agent:\n  system_template_path: system.txt\n")
    monkeypatch.chdir(tmp_path)
    config = load_config(config_path)
    assert config["agent"]["system_template"] == "System for {{ task }}"
    assert "system_template_path" not in config["agent"]
    agent = build_agent(config)
    agent.extra_template_vars["task"] = "review"
    assert (
        agent._render_template(agent.config.system_template)
        == "System for review"
    )


def test_system_template_file_absolute_path(tmp_path):
    template = tmp_path / "system.txt"
    template.write_text("System instructions", encoding="utf-8")
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(f"agent:\n  system_template_path: {template}\n")
    assert (
        load_config(config_path)["agent"]["system_template"]
        == "System instructions"
    )


def test_system_template_file_conflicts_with_inline(tmp_path):
    config_path = tmp_path / "agent.yaml"
    config_path.write_text(
        "agent:\n  system_template: inline\n"
        "  system_template_path: system.txt\n"
    )
    with pytest.raises(ValueError, match="Set only one"):
        load_config(config_path)


def test_missing_system_template_file(tmp_path):
    config_path = tmp_path / "agent.yaml"
    config_path.write_text("agent:\n  system_template_path: missing.txt\n")
    with pytest.raises(FileNotFoundError):
        load_config(config_path)


def test_resolve_class_dotted_path():
    cls = resolve_class("workshop.agent.default_agent.DefaultAgent", {})
    assert cls is DefaultAgent


def test_resolve_class_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown class"):
        resolve_class("nope", {"local": LocalEnvironment})


def test_unknown_config_key_raises(tmp_path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("environment:\n  not_a_field: 1\n")
    with pytest.raises(TypeError):
        build_agent(load_config(config_path))
