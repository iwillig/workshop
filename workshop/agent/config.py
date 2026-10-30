"""Build agents from YAML config files.

A config file has three sections, each feeding one component's dataclass
config. The ``*_class`` keys select the component by registry name or by a
dotted import path:

    agent:
      agent_class: interactive
      mode: confirm
      step_limit: 50
    environment:
      environment_class: local
      timeout: 30
    model:
      model_class: llm
      model_name: anthropic/claude-sonnet-4-5
"""

import importlib
from pathlib import Path

import yaml

from workshop.agent.default_agent import DefaultAgent
from workshop.agent.environments import DockerEnvironment, LocalEnvironment
from workshop.agent.interactive import InteractiveAgent
from workshop.agent.models import LlmModel

DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "default.yaml"

AGENT_CLASSES = {"default": DefaultAgent, "interactive": InteractiveAgent}
ENVIRONMENT_CLASSES = {"local": LocalEnvironment, "docker": DockerEnvironment}
MODEL_CLASSES = {"llm": LlmModel}


def resolve_class(name: str, registry: dict[str, type]) -> type:
    """Resolve a registry name like "local", or a dotted import path, to a class."""
    if name in registry:
        return registry[name]
    module_name, _, attribute = name.rpartition(".")
    if not module_name:
        raise ValueError(f"Unknown class {name!r}; expected one of {sorted(registry)} or a dotted import path")
    return getattr(importlib.import_module(module_name), attribute)


def load_config(path: Path | str) -> dict:
    """Load a YAML config file and normalize its component sections to dicts."""
    config = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Config file {path} must contain a mapping, got {type(config).__name__}")
    for section in ("agent", "environment", "model"):
        config[section] = dict(config.get(section) or {})
    return config


def build_agent(config: dict, **agent_overrides) -> DefaultAgent:
    """Instantiate the model, environment, and agent described by a config dict.

    Keyword arguments override keys in the agent section.
    """
    model_config = dict(config.get("model") or {})
    model_class = resolve_class(model_config.pop("model_class", "llm"), MODEL_CLASSES)
    model = model_class(**model_config)

    environment_config = dict(config.get("environment") or {})
    environment_class = resolve_class(environment_config.pop("environment_class", "local"), ENVIRONMENT_CLASSES)
    environment = environment_class(**environment_config)

    agent_config = dict(config.get("agent") or {})
    agent_class = resolve_class(agent_config.pop("agent_class", "interactive"), AGENT_CLASSES)
    return agent_class(model, environment, **agent_config | agent_overrides)
