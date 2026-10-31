"""An agent that displays model responses and command observations."""

from dataclasses import dataclass

import click

from workshop.agent.default_agent import AgentConfig, DefaultAgent


@dataclass
class InteractiveAgentConfig(AgentConfig):
    mode: str = "yolo"
    """Legacy setting: only unattended execution is supported."""


class InteractiveAgent(DefaultAgent):
    def __init__(
        self, model, env, *, config_class: type = InteractiveAgentConfig, **kwargs
    ):
        super().__init__(model, env, config_class=config_class, **kwargs)
        if self.config.mode != "yolo":
            raise ValueError(
                "Tool approval is no longer supported; remove agent.mode or set it to 'yolo'. "
                "Commands will run without confirmation."
            )

    def query(self) -> dict:
        message = super().query()
        click.secho(message.get("content", ""), fg="cyan")
        return message

    def execute_actions(self, message: dict) -> list[dict]:
        observations = super().execute_actions(message)
        for observation in observations:
            click.secho(observation.get("content", ""), fg="yellow")
        return observations
