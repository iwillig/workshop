"""Project-wide workshop configuration, independent of agent definitions."""

from pathlib import Path

import yaml


def load_workshop_config(path=None, *, cwd=None):
    """Load an explicit file or the nearest workshop.yaml with defaults."""
    if path is None:
        directory = Path(cwd or Path.cwd()).resolve()
        path = next(
            (
                parent / "workshop.yaml"
                for parent in (directory, *directory.parents)
                if (parent / "workshop.yaml").is_file()
            ),
            None,
        )
    if path is None:
        return {"llm": {"logging": {"enabled": False}}}
    path = Path(path).resolve()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid workshop configuration: {exc}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict) or set(data) - {"llm"}:
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
    return {"llm": {"logging": result}}
