"""Build agents from YAML config files.

A config file has three sections, each feeding one component's dataclass
config. The ``*_class`` keys select the component by registry name or by a
dotted import path:

    agent:
      agent_class: interactive
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

DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "default.yaml"


def resolve_class(name: str, registry: dict[str, type]) -> type:
    """Resolve a registry name or dotted import path to a class."""
    if name in registry:
        return registry[name]
    module_name, _, attribute = name.rpartition(".")
    if not module_name:
        raise ValueError(
            f"Unknown class {name!r}; expected one of "
            f"{sorted(registry)} or a dotted import path"
        )
    return getattr(importlib.import_module(module_name), attribute)


def load_config(path: Path | str, *, agent_name: str | None = None) -> dict:
    """Load YAML config and normalize component sections to dicts."""
    config = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(config, dict):
        raise ValueError(
            f"Config file {path} must contain a mapping, "
            f"got {type(config).__name__}"
        )
    if "agents" in config:
        if set(config) != {"agents"} or not isinstance(config["agents"], dict):
            raise ValueError(
                "Named configurations must contain only an agents mapping"
            )
        if agent_name is None:
            raise ValueError("Select an agent with --agent")
        if agent_name not in config["agents"]:
            raise ValueError(f"Unknown agent: {agent_name}")
        selected = config["agents"][agent_name]
        if not isinstance(selected, dict):
            raise ValueError("Agent definition must be a mapping")
        unknown = set(selected) - {
            "agent",
            "model",
            "environment",
            "prompts",
            "limits",
            "tools",
            "mcp_servers",
        }
        if unknown:
            raise ValueError(
                f"Unknown agent fields: {', '.join(sorted(unknown))}"
            )
        config = {
            key: value
            for key, value in selected.items()
            if key not in {"prompts", "limits"}
        }
        agent_options = dict(config.get("agent") or {})
        limits = selected.get("limits") or {}
        if not isinstance(limits, dict):
            raise ValueError("limits must be a mapping")
        if agent_options.keys() & limits.keys():
            raise ValueError("Agent fields and limits must not overlap")
        agent_options.update(limits)
        prompts = selected.get("prompts") or {}
        if not isinstance(prompts, dict) or set(prompts) - {
            "system",
            "system_file",
            "instance",
        }:
            raise ValueError("Unknown or invalid prompts configuration")
        for key, target in (
            ("system", "system_template"),
            ("system_file", "system_template_path"),
            ("instance", "instance_template"),
        ):
            if key in prompts:
                if target in agent_options:
                    raise ValueError(f"Duplicate prompt setting: {target}")
                agent_options[target] = prompts[key]
        config["agent"] = agent_options
    elif agent_name is not None:
        raise ValueError("--agent requires a named agents configuration")
    for section in ("agent", "environment", "model"):
        config[section] = dict(config.get(section) or {})
    agent = config["agent"]
    if "system_template_path" in agent:
        if "system_template" in agent:
            raise ValueError(
                "Set only one of system_template and system_template_path"
            )
        template_path = Path(agent.pop("system_template_path"))
        if not template_path.is_absolute():
            template_path = Path(path).resolve().parent / template_path
        agent["system_template"] = template_path.read_text(encoding="utf-8")
    return config


def build_agent(config: dict, **agent_overrides):
    """Instantiate the model, environment, and agent from a config dict.

    Keyword arguments override keys in the agent section.
    """
    from workshop.agent.default_agent import DefaultAgent
    from workshop.agent.environments import DockerEnvironment, LocalEnvironment
    from workshop.agent.interactive import InteractiveAgent
    from workshop.agent.mcp_runtime import MCPRuntime
    from workshop.agent.models import LlmModel
    from research_context.github_tools import GitHubTools, SPECS

    agent_classes = {"default": DefaultAgent, "interactive": InteractiveAgent}
    environment_classes = {
        "local": LocalEnvironment,
        "docker": DockerEnvironment,
    }
    model_classes = {"llm": LlmModel}
    tool_config = config.get("tools")
    if tool_config is not None:
        if not isinstance(tool_config, dict):
            raise ValueError("tools must be a mapping")
        for name, options in tool_config.items():
            if name not in {"read", "edit", "bash"} | SPECS.keys():
                raise ValueError(f"Unknown tool: {name}")
            if options not in ({}, None):
                raise ValueError(f"Tool options are not supported: {name}")
        if (config.get("model") or {}).get("protocol", "shell") != "native":
            raise ValueError("Tool selection requires model.protocol: native")
    model_config = dict(config.get("model") or {})
    model_class = resolve_class(
        model_config.pop("model_class", "llm"), model_classes
    )
    model = model_class(**model_config)
    logging = (config.get("workshop") or {}).get("llm", {}).get("logging", {})
    if logging.get("enabled"):
        configure = getattr(model, "configure_log_database", None)
        if configure is None:
            raise ValueError(
                "Configured model does not support workshop LLM logging"
            )
        configure(logging["database"])

    environment_config = dict(config.get("environment") or {})
    environment_class = resolve_class(
        environment_config.pop("environment_class", "local"),
        environment_classes,
    )
    environment = environment_class(**environment_config)

    agent_config = dict(config.get("agent") or {})
    agent_class = resolve_class(
        agent_config.pop("agent_class", "interactive"), agent_classes
    )
    if getattr(model.config, "protocol", None) == "native":
        agent_config.setdefault(
            "system_template",
            "You are a helpful coding assistant. Use the available tools "
            "to complete the task. When finished, respond with the result.",
        )
        agent_config.setdefault("instance_template", "Task: {{ task }}")
    agent = agent_class(model, environment, **agent_config | agent_overrides)
    if tool_config is not None:
        available = {tool.name for tool in agent.builtin_tools.tools}
        unavailable = set(tool_config) - available - SPECS.keys()
        if unavailable:
            raise ValueError(
                "Tools unavailable in this environment: "
                f"{', '.join(sorted(unavailable))}"
            )
        agent.builtin_tools.tools = [
            tool
            for tool in agent.builtin_tools.tools
            if tool.name in tool_config
        ]
        research_tools = GitHubTools(set(tool_config) & SPECS.keys())
        if research_tools.tools:
            agent.tool_providers.append(research_tools)
    servers = config.get("mcp_servers") or {}
    if servers:
        if not isinstance(servers, dict):
            raise ValueError("mcp_servers must be a mapping")
        if getattr(model.config, "protocol", None) != "native":
            raise ValueError("MCP servers require model.protocol: native")
        agent.mcp_runtime = MCPRuntime(servers)
    return agent
