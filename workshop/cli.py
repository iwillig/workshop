"""Compose the workshop component command groups."""

import click

from research_context.__main__ import cli as research_context_cli
from template_engine.cli import cli as template_engine_cli
from workshop.agent.cli import agent_commands
from workshop.browser import browser_commands


@click.group()
@click.option(
    "--workshop-config",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to the core workshop.yaml configuration.",
)
@click.pass_context
def cli(ctx, workshop_config):
    """Tools for the Common AI agent workshop."""
    from workshop.config import load_workshop_config

    try:
        ctx.ensure_object(dict)["workshop"] = load_workshop_config(
            path=workshop_config
        )
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc


cli.add_command(research_context_cli, name="research-context")
cli.add_command(browser_commands)
cli.add_command(template_engine_cli, name="template-engine")
cli.add_command(agent_commands)
