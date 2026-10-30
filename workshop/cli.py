"""Compose the workshop component command groups."""

import click

from research_context.__main__ import cli as research_context_cli
from template_engine.cli import cli as template_engine_cli
from workshop.agent.cli import agent_commands
from workshop.browser import browser_commands


@click.group()
def cli():
    """Tools for the Common AI agent workshop."""


cli.add_command(research_context_cli, name="research-context")
cli.add_command(browser_commands)
cli.add_command(template_engine_cli, name="template-engine")
cli.add_command(agent_commands)
