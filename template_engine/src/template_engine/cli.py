"""Generate projects from local Cookiecutter templates."""

from pathlib import Path

import click
from cookiecutter.exceptions import CookiecutterException
from cookiecutter.main import cookiecutter


@click.group()
def cli():
    """Generate projects from local templates."""


@cli.command("list")
def list_templates():
    """List templates bundled with the engine."""
    click.echo("python-project")


@cli.command("create")
@click.argument("template")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, exists=True, path_type=Path),
    default=".",
    show_default=True,
)
@click.option(
    "--no-input", is_flag=True, help="Use template defaults without prompting."
)
@click.option(
    "--value",
    "values",
    multiple=True,
    metavar="KEY=VALUE",
    help="Override a template variable; may be repeated.",
)
def create(template, output_dir, no_input, values):
    """Generate from a bundled name or local TEMPLATE directory."""
    if template == "python-project":
        path = Path(__file__).parent / "templates" / "python-project"
    else:
        path = Path(template).expanduser().resolve()
    if not path.is_dir() or not (path / "cookiecutter.json").is_file():
        raise click.ClickException(
            "Template must be a local directory containing cookiecutter.json."
        )
    context = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key:
            raise click.BadParameter(
                "Expected KEY=VALUE.", param_hint="--value"
            )
        context[key] = item
    try:
        result = cookiecutter(
            str(path),
            no_input=no_input,
            extra_context=context,
            output_dir=str(output_dir.resolve()),
            accept_hooks=False,
            default_config=True,
        )
    except (CookiecutterException, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Created {result}")
