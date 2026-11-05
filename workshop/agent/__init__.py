"""A minimal coding agent built on Simon Willison's llm library.

This is a re-implementation of mini-swe-agent (MIT licensed,
https://mini-swe-agent.com) with the litellm model layer replaced by the llm
library, so any model with an llm plugin (Anthropic, OpenAI, Ollama, ...) can
drive the agent. The design commitments are the same as upstream:

- supports legacy fenced shell commands and native LLM tool calls
- the message history doubles as the trajectory
- execution environments provide local or container-based command execution
"""

from workshop.agent.default_agent import AgentConfig, DefaultAgent
from workshop.agent.environments import DockerEnvironment, LocalEnvironment
from workshop.agent.exceptions import (
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
