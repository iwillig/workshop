"""A minimal coding agent built on Simon Willison's llm library.

This is a re-implementation of mini-swe-agent (MIT licensed,
https://mini-swe-agent.com) with the litellm model layer replaced by the llm
library, so any model with an llm plugin (Anthropic, OpenAI, Ollama, ...) can
drive the agent. The design commitments are the same as upstream:

- bash is the only tool; actions are parsed from fenced text, not tool calls
- the message history is strictly linear and doubles as the trajectory
- every action runs as an independent subprocess, so sandboxing is one method
"""

from workshop.agent.config import DEFAULT_CONFIG_PATH, build_agent, load_config
from workshop.agent.default_agent import AgentConfig, DefaultAgent
from workshop.agent.environments import DockerEnvironment, LocalEnvironment
from workshop.agent.exceptions import (
    CommandRejected,
    FormatError,
    InterruptAgentFlow,
    LimitsExceeded,
    Submitted,
    TimeExceeded,
    UserInterruption,
)
from workshop.agent.interactive import InteractiveAgent
from workshop.agent.models import LlmModel

__all__ = [
    "AgentConfig",
    "CommandRejected",
    "DEFAULT_CONFIG_PATH",
    "build_agent",
    "load_config",
    "DefaultAgent",
    "DockerEnvironment",
    "FormatError",
    "InteractiveAgent",
    "InterruptAgentFlow",
    "LimitsExceeded",
    "LlmModel",
    "LocalEnvironment",
    "Submitted",
    "TimeExceeded",
    "UserInterruption",
]

__version__ = "0.1.0"
