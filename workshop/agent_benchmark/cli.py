"""CLI for trusted, report-only local benchmarks."""

import json
from pathlib import Path

import click

from workshop.agent_benchmark.local import run_suite
from workshop.agent_eval.reviews import load_report, record_review
from workshop.agent_config import load_config


@click.group(name="benchmark")
def benchmark_commands():
    """Run trusted local benchmarks and inspect private reports."""


@benchmark_commands.command("run")
@click.option(
    "--suite",
    required=True,
    type=click.Choice(["coding-v1", "review-v1", "coding-v2", "review-v2"]),
)
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--agent", "agent_name", required=True)
@click.option("--storage", required=True, type=click.Path(path_type=Path))
@click.option(
    "--local",
    is_flag=True,
    help="Acknowledge that host execution is not isolated.",
)
@click.pass_context
def run_command(ctx, suite, config, agent_name, storage, local):
    """Execute a named agent on a trusted local fixture."""
    if not local:
        raise click.UsageError("Pass --local to acknowledge host execution")
    click.echo(
        "WARNING: local execution is not isolated. Agent tools and generated "
        "code have your user permissions; remote models may receive "
        "fixture data.",
        err=True,
    )
    try:
        agent_config = load_config(config, agent_name=agent_name)
        agent_config["workshop"] = ctx.obj.get("workshop", {})
        report = run_suite(
            suite, agent_config, agent_name, storage, local=True
        )
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report, indent=2))


@benchmark_commands.command("report")
@click.argument("run_id")
@click.option("--storage", required=True, type=click.Path(path_type=Path))
def report_command(run_id, storage):
    """Display a previously stored report."""
    try:
        report = load_report(storage, run_id)
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report, indent=2))


@benchmark_commands.command("review")
@click.argument("run_id")
@click.option("--case", "case_id", required=True)
@click.option(
    "--decision",
    required=True,
    type=click.Choice(["pass", "fail", "inconclusive"]),
)
@click.option("--reviewer", required=True)
@click.option("--rationale", required=True)
@click.option("--storage", required=True, type=click.Path(path_type=Path))
def review_command(run_id, case_id, decision, reviewer, rationale, storage):
    """Record a human judgment without changing the original run."""
    try:
        review = record_review(
            storage, run_id, case_id, decision, reviewer, rationale
        )
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(review, indent=2))
