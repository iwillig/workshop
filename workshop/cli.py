"""Compose the workshop component command groups."""

import click

from research_context.__main__ import cli as research_context_cli
from template_engine.cli import cli as template_engine_cli
from workshop.agent.cli import agent_commands
from workshop.agent_benchmark.cli import benchmark_commands
from workshop.agent_eval.cli import eval_commands
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


@cli.group(name="config")
def config_commands():
    """Inspect project configuration."""


@config_commands.command(name="validate")
def validate_config():
    """Validate the discovered or explicitly selected project configuration."""
    from workshop.config import find_workshop_config

    context = click.get_current_context()
    explicit = context.find_root().params.get("workshop_config")
    path = explicit or find_workshop_config()
    click.echo(
        f"Valid configuration: {path}" if path else "Using built-in defaults"
    )


@config_commands.command(name="show")
@click.pass_context
def show_config(ctx):
    """Show normalized settings with scalar values redacted."""
    import yaml

    def redact(value):
        if isinstance(value, dict):
            return {str(k): redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        return "<redacted>" if value is not None else None

    click.echo(
        yaml.safe_dump(
            redact((ctx.obj or {}).get("workshop", {})), sort_keys=False
        )
    )


cli.add_command(research_context_cli, name="research-context")
cli.add_command(browser_commands)
cli.add_command(template_engine_cli, name="template-engine")
cli.add_command(agent_commands)
cli.add_command(benchmark_commands)
cli.add_command(eval_commands)
