"""CLI for private trace reviews and human-judged proposals."""

import json
from pathlib import Path

import click

from workshop.config import select_agent, storage_option
from workshop.agent_eval.proposals import (
    load_proposals,
    load_trace_review,
    record_proposal,
    record_proposal_decision,
)
from workshop.agent_eval.review_runner import (
    DEFAULT_BUDGET,
    review_trace,
)


@click.group(name="eval")
def eval_commands():
    """Review stored traces and manage human-judged proposals."""


@eval_commands.command("review-trace")
@click.argument("run_id")
@click.option("--agent", "agent_name")
@click.option("--storage", type=click.Path(path_type=Path))
@click.option("--budget", type=click.IntRange(min=1), default=None)
@click.pass_context
def review_trace_command(ctx, run_id, agent_name, storage, budget):
    """Review a stored trace with an experimental model configuration."""
    click.echo(
        "WARNING: trace review is not network-isolated; loopback and proxy "
        "settings do not prove local-only execution. Use only synthetic or "
        "non-sensitive traces until the boundary is verified.",
        err=True,
    )
    try:
        project = (ctx.obj or {}).get("workshop", {})
        budget = budget or project.get("evaluation", {}).get(
            "budget", DEFAULT_BUDGET
        )
        storage = storage or project.get("benchmark", {}).get("storage")
        if not storage:
            raise ValueError("Set --storage or benchmark.storage")
        agent_name, reviewer_config = select_agent(project, agent_name)
        reviewer_config["workshop"] = project
        payload = review_trace(storage, run_id, reviewer_config, budget)
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(payload, indent=2))
    if payload["status"] != "completed":
        raise click.exceptions.Exit(1)


@eval_commands.command("inspect")
@click.argument("review_id")
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
def inspect_command(review_id, storage):
    """Display a stored trace review."""
    try:
        payload = load_trace_review(storage, review_id)
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(payload, indent=2))


@eval_commands.command("propose")
@click.argument("review_id")
@click.option(
    "--kind",
    required=True,
    type=click.Choice(["eval-case", "prompt-change", "skill-note"]),
)
@click.option("--observation", type=int, required=True)
@click.option("--rationale", required=True)
@click.option("--payload", default="{}", help="Descriptive JSON object.")
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
def propose_command(review_id, kind, observation, rationale, payload, storage):
    """Record a descriptive proposal linked to a reviewed observation."""
    try:
        candidate = json.loads(payload)
        if not isinstance(candidate, dict):
            raise ValueError("Payload must be a JSON object")
        proposal = record_proposal(
            storage,
            review_id,
            kind,
            rationale,
            [{"review_id": review_id, "observation": observation}],
            candidate,
        )
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(proposal, indent=2))


@eval_commands.command("decide")
@click.argument("proposal_id")
@click.option(
    "--decision",
    required=True,
    type=click.Choice(["accept", "reject", "revise"]),
)
@click.option("--reviewer", required=True)
@click.option("--rationale", required=True)
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
def decide_command(proposal_id, decision, reviewer, rationale, storage):
    """Record a human decision without changing the proposal."""
    try:
        payload = record_proposal_decision(
            storage, proposal_id, decision, reviewer, rationale
        )
    except (ValueError, OSError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(payload, indent=2))


@eval_commands.command("proposals")
@click.option(
    "--storage", type=click.Path(path_type=Path), callback=storage_option
)
def proposals_command(storage):
    """List proposals with their decision history."""
    try:
        payload = load_proposals(storage)
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(payload, indent=2))
