"""Compose the workshop component command groups."""

import click

from research_context.__main__ import cli as research_context_cli


@click.group()
def cli():
    """Tools for the Common AI agent workshop."""


cli.add_command(research_context_cli, name="research-context")
