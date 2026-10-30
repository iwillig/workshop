"""A human-in-the-loop agent: confirm each command before it runs."""

from dataclasses import dataclass

import click

from workshop.agent.default_agent import AgentConfig, DefaultAgent
from workshop.agent.exceptions import CommandRejected


@dataclass
class InteractiveAgentConfig(AgentConfig):
    mode: str = "confirm"
    """"confirm" asks before every command; "yolo" runs them immediately."""


class InteractiveAgent(DefaultAgent):
    def __init__(self, model, env, *, config_class: type = InteractiveAgentConfig, **kwargs):
        super().__init__(model, env, config_class=config_class, **kwargs)

    def query(self) -> dict:
        message = super().query()
        click.secho(message.get("content", ""), fg="cyan")
        return message

    def execute_actions(self, message: dict) -> list[dict]:
        if self.config.mode == "confirm":
            for action in message.get("extra", {}).get("actions", []):
                answer = click.prompt(
                    f"Run `{action['command']}`? [Enter to run, or type feedback to reject]",
                    default="",
                    show_default=False,
                )
                if answer.strip():
                    raise CommandRejected(
                        {
                            "role": "user",
                            "content": f"The user rejected this command. Feedback: {answer}",
                            "extra": {"interrupt_type": "CommandRejected"},
                        }
                    )
        observations = super().execute_actions(message)
        for observation in observations:
            click.secho(observation.get("content", ""), fg="yellow")
        return observations
