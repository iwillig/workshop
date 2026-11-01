"""Compatibility imports for the configuration subsystem.

New code should import from :mod:`workshop.agent_config`.
"""

from workshop.agent_config import (
    DEFAULT_CONFIG_PATH,
    build_agent,
    load_config,
    resolve_class,
)

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "build_agent",
    "load_config",
    "resolve_class",
]
