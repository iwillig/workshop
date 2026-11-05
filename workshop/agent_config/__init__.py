"""Build named agents from project configuration.

Agent, environment and model sections feed their respective component configs.
The ``*_class`` keys select a registry name or a dotted import path.
"""

import importlib
from pathlib import Path


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
    """Load a named agent from a complete workshop project configuration."""
    from workshop.config import load_workshop_config, select_agent

    return select_agent(load_workshop_config(path), agent_name)[1]


def normalize_config(
    config: dict, *, path: Path | str, agent_name=None
) -> dict:
    """Normalize a named agent from project configuration."""
    if not isinstance(config, dict):
        raise ValueError(
            f"Config file {path} must contain a mapping, "
            f"got {type(config).__name__}"
        )
    if "agents" not in config:
        raise ValueError(
            "Agent definitions must be under agents in workshop.yaml"
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
        if config.get("agent") is not None and not isinstance(
            config["agent"], dict
        ):
            raise ValueError("agent must be a mapping")
        agent_options = dict(config.get("agent") or {})
        limits = selected.get("limits", {})
        if not isinstance(limits, dict):
            raise ValueError("limits must be a mapping")
        if agent_options.keys() & limits.keys():
            raise ValueError("Agent fields and limits must not overlap")
        agent_options.update(limits)
        prompts = selected.get("prompts", {})
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
        value = config.get(section)
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"{section} must be a mapping")
        config[section] = dict(value or {})
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


def validate_project_agent(config: dict, *, name: str) -> None:
    """Validate built-in settings without initializing models or tools."""
    from dataclasses import fields
    from typing import get_type_hints

    from pydantic import TypeAdapter, ValidationError

    from workshop.agent.default_agent import AgentConfig
    from workshop.agent.interactive import InteractiveAgentConfig
    from workshop.agent.environments import (
        LocalEnvironmentConfig,
        DockerEnvironmentConfig,
    )
    from workshop.agent.models import LlmModelConfig
    from research_context.github_tools import SPECS

    sections = (
        (
            "agent",
            "agent_class",
            {"default": AgentConfig, "interactive": InteractiveAgentConfig},
            "interactive",
        ),
        (
            "environment",
            "environment_class",
            {
                "local": LocalEnvironmentConfig,
                "docker": DockerEnvironmentConfig,
            },
            "local",
        ),
        ("model", "model_class", {"llm": LlmModelConfig}, "llm"),
    )
    for section, selector, classes, default in sections:
        options = config[section]
        kind = options.get(selector, default)
        if not isinstance(kind, str) or not kind:
            raise ValueError(
                f"agents.{name}.{section}.{selector} must be a string"
            )
        if kind in classes:
            unknown = (
                set(options)
                - {selector}
                - {f.name for f in fields(classes[kind])}
            )
            if unknown:
                raise ValueError(
                    f"agents.{name}.{section}: "
                    f"unknown fields {sorted(unknown)}"
                )
            hints = get_type_hints(classes[kind])
            for key, value in options.items():
                if key == selector:
                    continue
                # YAML paths are strings; convert them only when consumed.
                if section == "agent" and key == "output_path":
                    if value is not None and not isinstance(value, str):
                        raise ValueError(
                            f"agents.{name}.agent.output_path must be a path"
                        )
                    continue
                try:
                    TypeAdapter(hints[key]).validate_python(value, strict=True)
                except ValidationError as exc:
                    raise ValueError(
                        f"agents.{name}.{section}.{key}: invalid value"
                    ) from exc
        elif "." not in kind:
            raise ValueError(
                f"agents.{name}.{section}: unknown class {kind!r}"
            )
    agent = config["agent"]
    if (
        agent.get("agent_class", "interactive") == "interactive"
        and agent.get("mode", "yolo") != "yolo"
    ):
        raise ValueError(
            f"agents.{name}.agent.mode: approval is not supported"
        )
    if (
        agent.get("agent_class", "interactive") in ("default", "interactive")
        and agent.get("max_parallel_tools", 4) < 1
    ):
        raise ValueError(
            f"agents.{name}.agent.max_parallel_tools must be positive"
        )
    environment = config["environment"]
    if (
        environment.get("environment_class", "local") in ("local", "docker")
        and environment.get("timeout", 30) <= 0
    ):
        raise ValueError(f"agents.{name}.environment.timeout must be positive")
    model = config["model"]
    if model.get("protocol", "shell") not in ("shell", "native"):
        raise ValueError(
            f"agents.{name}.model.protocol must be shell or native"
        )
    if "retry_attempts" in model and (
        type(model["retry_attempts"]) is not int or model["retry_attempts"] < 1
    ):
        raise ValueError(
            f"agents.{name}.model.retry_attempts must be positive"
        )
    tools = config.get("tools")
    if tools is not None:
        if not isinstance(tools, dict):
            raise ValueError(f"agents.{name}.tools must be a mapping")
        for tool, options in tools.items():
            if tool not in {
                "read",
                "edit",
                "bash",
            } | SPECS.keys() or options not in ({}, None):
                raise ValueError(f"agents.{name}.tools: invalid tool {tool!r}")
    servers = config.get("mcp_servers")
    if servers is not None and not isinstance(servers, dict):
        raise ValueError(f"agents.{name}.mcp_servers must be a mapping")
    if (tools is not None or servers) and model.get(
        "protocol", "shell"
    ) != "native":
        raise ValueError(
            f"agents.{name}: tools and MCP require model.protocol: native"
        )
    for server_name, server in (servers or {}).items():
        if not isinstance(server, dict) or server.get("transport") not in (
            "stdio",
            "http",
        ):
            raise ValueError(
                f"agents.{name}.mcp_servers.{server_name}: invalid transport"
            )
        required = "command" if server["transport"] == "stdio" else "url"
        if not isinstance(server.get(required), str) or not server[required]:
            raise ValueError(
                f"agents.{name}.mcp_servers.{server_name}."
                f"{required} is required"
            )
        allowed = (
            {"transport", "command", "args", "env", "env_from", "cwd"}
            if required == "command"
            else {"transport", "url", "headers_env"}
        )
        if set(server) - allowed:
            raise ValueError(
                f"agents.{name}.mcp_servers.{server_name}: unknown fields"
            )
        if "args" in server and (
            not isinstance(server["args"], list)
            or not all(isinstance(arg, str) for arg in server["args"])
        ):
            raise ValueError(
                f"agents.{name}.mcp_servers.{server_name}.args "
                "must be a list of strings"
            )
        if "cwd" in server and not isinstance(server["cwd"], str):
            raise ValueError(
                f"agents.{name}.mcp_servers.{server_name}.cwd must be a string"
            )
        for field in ("env", "env_from", "headers_env"):
            if field in server and (
                not isinstance(server[field], dict)
                or not all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in server[field].items()
                )
            ):
                raise ValueError(
                    f"agents.{name}.mcp_servers.{server_name}.{field} "
                    "must map strings to strings"
                )


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
