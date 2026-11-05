"""Project configuration discovery, normalization, and CLI defaults."""

from pathlib import Path

import yaml


def find_workshop_config(*, cwd=None):
    """Return the nearest project configuration, if present."""
    directory = Path(cwd or Path.cwd()).resolve()
    return next(
        (
            parent / "workshop.yaml"
            for parent in (directory, *directory.parents)
            if (parent / "workshop.yaml").is_file()
        ),
        None,
    )


def load_workshop_config(path=None, *, cwd=None):
    """Load an explicit file or the nearest workshop.yaml with defaults."""
    if path is None:
        path = find_workshop_config(cwd=cwd)
    if path is None:
        return {"llm": {"logging": {"enabled": False}}}
    path = Path(path).resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid workshop configuration: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict) or set(data) - {
        "version",
        "llm",
        "agents",
        "default_agent",
        "benchmark",
        "evaluation",
        "browser",
    }:
        raise ValueError("workshop.yaml must contain only recognized fields")
    llm = data.get("llm", {})
    if not isinstance(llm, dict) or set(llm) - {"logging"}:
        raise ValueError("llm must contain only recognized fields")
    logging = llm.get("logging", {})
    if not isinstance(logging, dict) or set(logging) - {"enabled", "database"}:
        raise ValueError("llm.logging must contain only enabled and database")
    enabled = logging.get("enabled", False)
    if type(enabled) is not bool:
        raise ValueError("llm.logging.enabled must be a boolean")
    database = logging.get("database")
    if database is not None and (
        not isinstance(database, str) or not database.strip()
    ):
        raise ValueError("llm.logging.database must be a nonempty path")
    if enabled and not database:
        raise ValueError(
            "llm.logging.database is required when logging is enabled"
        )
    result = {"enabled": enabled}
    if database:
        db_path = Path(database).expanduser()
        result["database"] = str((path.parent / db_path).absolute())
    output = {"llm": {"logging": result}}
    if "agents" in data and "version" not in data:
        raise ValueError("version: 1 is required when defining agents")
    version = data.get("version", 1)
    if type(version) is not int or version != 1:
        raise ValueError("version must be 1")
    agents = data.get("agents", {})
    if not isinstance(agents, dict) or any(
        not isinstance(name, str) or not name for name in agents
    ):
        raise ValueError("agents must be a mapping of nonempty names")
    if agents:
        from workshop.agent_config import (
            normalize_config,
            validate_project_agent,
        )

        output["agents"] = {}
        for name in agents:
            try:
                agent = normalize_config(
                    {"agents": agents}, path=path, agent_name=name
                )
                validate_project_agent(agent, name=name)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"agents.{name}: {exc}") from exc
            output["agents"][name] = agent
    default_agent = data.get("default_agent")
    if default_agent is not None:
        if not isinstance(default_agent, str) or default_agent not in agents:
            raise ValueError("default_agent must name an agent in agents")
        output["default_agent"] = default_agent
    benchmark = data.get("benchmark", {})
    if not isinstance(benchmark, dict) or set(benchmark) - {
        "storage",
        "suite",
    }:
        raise ValueError("benchmark must contain only storage and suite")
    if "suite" in benchmark:
        if not isinstance(benchmark["suite"], str) or benchmark[
            "suite"
        ] not in {
            "coding-v1",
            "review-v1",
            "coding-v2",
            "review-v2",
            "coding-v3",
            "review-v3",
            "pr-review-v5",
        }:
            raise ValueError("benchmark.suite must name a supported suite")
        output.setdefault("benchmark", {})["suite"] = benchmark["suite"]
    if "storage" in benchmark:
        storage = benchmark["storage"]
        if not isinstance(storage, str) or not storage.strip():
            raise ValueError("benchmark.storage must be a nonempty path")
        output.setdefault("benchmark", {})["storage"] = str(
            (path.parent / Path(storage).expanduser()).absolute()
        )
    evaluation = data.get("evaluation", {})
    if not isinstance(evaluation, dict) or set(evaluation) - {"budget"}:
        raise ValueError("evaluation must contain only budget")
    if "budget" in evaluation:
        if type(evaluation["budget"]) is not int or evaluation["budget"] < 1:
            raise ValueError("evaluation.budget must be a positive integer")
        output["evaluation"] = dict(evaluation)
    browser = data.get("browser", {})
    if not isinstance(browser, dict) or set(browser) - {"width", "height"}:
        raise ValueError("browser must contain only width and height")
    for key, value in browser.items():
        if type(value) is not int or value < 1:
            raise ValueError(f"browser.{key} must be a positive integer")
    if browser:
        output["browser"] = dict(browser)
    return output


def select_agent(project, name=None, *, model_override=None):
    """Return an independent named project agent, requiring an LLM model ID."""
    from copy import deepcopy

    name = name or project.get("default_agent")
    if not name:
        raise ValueError("Select an agent with --agent or default_agent")
    if name not in project.get("agents", {}):
        raise ValueError(f"Unknown agent: {name}")
    config = deepcopy(project["agents"][name])
    model = config["model"]
    if model.get("model_class", "llm") == "llm" and not (
        model_override or model.get("model_name")
    ):
        raise ValueError(
            f"agents.{name}.model.model_name or --model is required"
        )
    return name, config


def storage_option(ctx, param, value):
    """Use an explicit path or the project benchmark storage directory."""
    import click

    project = (ctx.obj or {}).get("workshop", {})
    value = value or project.get("benchmark", {}).get("storage")
    if value is None and not ctx.resilient_parsing:
        raise click.BadParameter("set --storage or benchmark.storage")
    return Path(value) if value else None
