"""CLI for trusted, report-only local benchmarks."""

import json
from pathlib import Path

import click

from workshop.agent_benchmark.compare import compare_reports
from workshop.agent_benchmark.local import run_suite
from workshop.agent_eval.reviews import load_report, record_review
from workshop.agent_eval.trace import load_trace
from workshop.config import select_agent, storage_option


@click.group(name="benchmark")
def benchmark_commands():
    """Run trusted local benchmarks and inspect private reports."""


@benchmark_commands.command("run")
@click.option(
    "--suite",
    type=click.Choice(
        [
            "coding-v1",
            "review-v1",
            "coding-v2",
            "review-v2",
            "coding-v3",
            "review-v3",
            "pr-review-v5",
        ]
    ),
)
@click.option("--agent", "agent_name")
@click.option("--storage", type=click.Path(path_type=Path))
@click.option(
    "--local",
    is_flag=True,
    help="Acknowledge that host execution is not isolated.",
)
@click.option(
    "--trace",
    is_flag=True,
    help="Store agent trajectories in private storage.",
)
@click.pass_context
def run_command(ctx, suite, agent_name, storage, local, trace):
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
        project = (ctx.obj or {}).get("workshop", {})
        suite = suite or project.get("benchmark", {}).get("suite")
        if not suite:
            raise ValueError("Set --suite or benchmark.suite")
        storage = storage or project.get("benchmark", {}).get("storage")
        if not storage:
            raise ValueError("Set --storage or benchmark.storage")
        agent_name, agent_config = select_agent(project, agent_name)
        agent_config["workshop"] = project
        report = run_suite(
            suite,
            agent_config,
            agent_name,
            storage,
            local=True,
            capture_trace=trace,
        )
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report, indent=2))
    if report["counts"]["infrastructure_error"]:
        click.echo(
            "Benchmark completed with infrastructure errors; "
            "the report was saved.",
            err=True,
        )
        raise click.exceptions.Exit(1)


@benchmark_commands.command("trace")
@click.argument("run_id")
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
def trace_command(run_id, storage):
    """Display the trajectories stored for a run."""
    try:
        record = load_trace(storage, run_id)
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(record, indent=2))


@benchmark_commands.command("compare")
@click.argument("run_id_a")
@click.argument("run_id_b")
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
def compare_command(run_id_a, run_id_b, storage):
    """Compare two stored runs of the same suite version."""
    try:
        comparison = compare_reports(storage, run_id_a, run_id_b)
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(comparison, indent=2))


@benchmark_commands.command("report")
@click.argument("run_id")
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
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
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
def review_command(run_id, case_id, decision, reviewer, rationale, storage):
    """Record a human judgment without changing the original run."""
    try:
        review = record_review(
            storage, run_id, case_id, decision, reviewer, rationale
        )
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(review, indent=2))
