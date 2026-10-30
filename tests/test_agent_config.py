import pytest

from workshop.agent.config import DEFAULT_CONFIG_PATH, build_agent, load_config, resolve_class
from workshop.agent.default_agent import DefaultAgent
from workshop.agent.environments import LocalEnvironment
from workshop.agent.interactive import InteractiveAgent
from workshop.agent.models import LlmModel


def test_default_config_builds_interactive_agent():
    agent = build_agent(load_config(DEFAULT_CONFIG_PATH))
    assert isinstance(agent, InteractiveAgent)
    assert agent.config.mode == "confirm"
    assert agent.config.step_limit == 50
    assert isinstance(agent.env, LocalEnvironment)
    assert agent.env.config.env["PAGER"] == "cat"
    assert isinstance(agent.model, LlmModel)


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
    agent = build_agent(config, step_limit=2, mode="yolo")
    assert agent.config.step_limit == 2
    assert agent.config.mode == "yolo"


def test_empty_sections_are_normalized(tmp_path):
    config_path = tmp_path / "sparse.yaml"
    config_path.write_text("agent:\n")
    config = load_config(config_path)
    assert config["agent"] == {}
    assert config["environment"] == {}
    agent = build_agent(config)
    assert isinstance(agent, InteractiveAgent)


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
