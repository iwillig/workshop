"""Serialization helpers, ported from mini-swe-agent."""

import dataclasses
from pathlib import Path
from typing import Any


def recursive_merge(*dictionaries: dict | None) -> dict:
    """Merge dictionaries recursively; later dictionaries take precedence."""
    result: dict[str, Any] = {}
    for dictionary in dictionaries:
        if dictionary is None:
            continue
        for key, value in dictionary.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = recursive_merge(result[key], value)
            else:
                result[key] = value
    return result


def config_as_dict(config) -> dict:
    """Serialize a dataclass config to a json-compatible dictionary."""

    def convert(value):
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    return convert(dataclasses.asdict(config))
