"""Language model layer backed by the llm library (replaces litellm upstream).

The llm library tracks multi-turn state in a Conversation, so LlmModel keeps
one internally and sends only the user content added since the previous
assistant reply. The agent's message list stays the canonical trajectory; a
guard raises if the two ever drift apart (e.g. a model instance reused across
runs without reset()).
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any

import llm
from jinja2 import StrictUndefined, Template

from workshop.agent.exceptions import FormatError
from workshop.agent.prompts import DEFAULT_FORMAT_ERROR_TEMPLATE, DEFAULT_OBSERVATION_TEMPLATE
from workshop.agent.serialize import config_as_dict

DEFAULT_ACTION_REGEX = r"```mswea_bash_command\s*\n(.*?)\n```"


def parse_regex_actions(
    content: str, *, action_regex: str, format_error_template: str, template_kwargs: dict | None = None
) -> list[dict]:
    """Parse actions from text content using regex. Raises FormatError if not exactly one action."""
    actions = [a.strip() for a in re.findall(action_regex, content, re.DOTALL)]
    if len(actions) != 1:
        error_msg = f"Expected exactly 1 action, found {len(actions)}."
        raise FormatError(
            {
                "role": "user",
                "content": Template(format_error_template, undefined=StrictUndefined).render(
                    actions=actions, error=error_msg, **(template_kwargs or {})
                ),
                "extra": {
                    "interrupt_type": "FormatError",
                    "n_actions": len(actions),
                    "model_response": content,
                },
            }
        )
    return [{"command": action} for action in actions]


def format_observation_messages(
    outputs: list[dict], *, observation_template: str, template_vars: dict | None = None
) -> list[dict]:
    """Format execution outputs into user observation messages."""
    results = []
    for output in outputs:
        content = Template(observation_template, undefined=StrictUndefined).render(
            output=output, **(template_vars or {})
        )
        results.append(
            {
                "role": "user",
                "content": content,
                "extra": {
                    "raw_output": output.get("output", ""),
                    "returncode": output.get("returncode"),
                    "timestamp": time.time(),
                    "exception_info": output.get("exception_info"),
                    **output.get("extra", {}),
                },
            }
        )
    return results


def extract_prompt(messages: list[dict], n_previous_responses: int) -> tuple[str | None, str]:
    """Return (system, prompt) for the next llm call from the agent's message list.

    The prompt is every user message appended since the last assistant reply;
    the system message is sent only with the first call of a conversation.
    """
    n_assistant = sum(1 for m in messages if m.get("role") == "assistant")
    if n_assistant != n_previous_responses:
        raise RuntimeError(
            "LlmModel is stateful: the message history no longer matches its conversation. "
            "Call reset() (or create a fresh model) before starting a new run."
        )
    new_user_contents = []
    for message in reversed(messages):
        role = message.get("role")
        if role == "assistant":
            break
        if role == "user":
            new_user_contents.append(message["content"])
    if not new_user_contents:
        raise ValueError("No new user message to send to the model.")
    system = None
    if n_previous_responses == 0 and messages and messages[0].get("role") == "system":
        system = messages[0]["content"]
    return system, "\n\n".join(reversed(new_user_contents))


@dataclass
class LlmModelConfig:
    model_name: str | None = None
    """An llm model id or alias. None uses the llm library's default model."""
    model_options: dict[str, Any] = field(default_factory=dict)
    """Options passed to llm's prompt() call, e.g. temperature."""
    input_cost_per_mtok: float = 0.0
    output_cost_per_mtok: float = 0.0
    """Dollar cost per million tokens; llm has no pricing tables, so cost is 0 unless set."""
    action_regex: str = DEFAULT_ACTION_REGEX
    format_error_template: str = DEFAULT_FORMAT_ERROR_TEMPLATE
    observation_template: str = DEFAULT_OBSERVATION_TEMPLATE
    retry_attempts: int = 3
    retry_wait_seconds: float = 10.0


class LlmModel:
    def __init__(self, *, config_class: type = LlmModelConfig, **kwargs):
        self.config = config_class(**kwargs)
        self._model = llm.get_model(self.config.model_name)
        self.reset()

    def reset(self):
        """Start a fresh conversation, e.g. for a new agent run."""
        self._conversation = self._model.conversation()

    def query(self, messages: list[dict], **kwargs) -> dict:
        system, prompt = extract_prompt(messages, len(self._conversation.responses))
        options = self.config.model_options | kwargs
        last_error: Exception | None = None
        for attempt in range(self.config.retry_attempts):
            if attempt:
                time.sleep(self.config.retry_wait_seconds * attempt)
            try:
                response = self._conversation.prompt(prompt, system=system, **options)
                content = response.text()
                break
            except Exception as e:
                last_error = e
        else:
            raise last_error  # type: ignore[misc]
        cost_extra = self._cost(response)
        try:
            actions = parse_regex_actions(
                content,
                action_regex=self.config.action_regex,
                format_error_template=self.config.format_error_template,
            )
        except FormatError as e:
            # The call was billed before parsing failed; persist cost and response on the error.
            e.messages[0]["extra"].update(cost_extra)
            e.messages[0]["extra"]["response"] = content
            raise
        return {
            "role": "assistant",
            "content": content,
            "extra": {"actions": actions, "timestamp": time.time(), **cost_extra},
        }

    def _cost(self, response) -> dict:
        usage: dict[str, int | None] = {}
        try:
            u = response.usage()
            usage = {"input": u.input, "output": u.output}
        except Exception:
            pass
        cost = (
            (usage.get("input") or 0) * self.config.input_cost_per_mtok
            + (usage.get("output") or 0) * self.config.output_cost_per_mtok
        ) / 1_000_000
        return {"cost": cost, "usage": usage}

    def format_message(self, **kwargs) -> dict:
        return dict(kwargs)

    def format_observation_messages(
        self, message: dict, outputs: list[dict], template_vars: dict | None = None
    ) -> list[dict]:
        return format_observation_messages(
            outputs, observation_template=self.config.observation_template, template_vars=template_vars
        )

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return config_as_dict(self.config)

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "model": config_as_dict(self.config),
                    "model_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                },
            }
        }
