"""Command line interface for the workshop mini coding agent."""

import os
import sys
from pathlib import Path

import click
from rich.console import Console

from workshop.agent_config import DEFAULT_CONFIG_PATH, build_agent, load_config


@click.group(name="agent")
def agent_commands():
    """Run the workshop coding agent (a mini-swe-agent port using llm)."""


@agent_commands.command(name="run")
@click.option(
    "-t", "--task", required=True, help="The task for the agent to solve."
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="YAML config file (default: the packaged default config).",
)
@click.option(
    "--agent",
    "agent_name",
    default=None,
    help="Name of an agent in the YAML configuration.",
)
@click.option(
    "-m",
    "--model",
    "model_name",
    default=None,
    help="An llm model id or alias (default: llm's default model).",
)
@click.option(
    "-y",
    "--yolo",
    is_flag=True,
    help="Deprecated; commands already run without confirmation.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Save the trajectory to this file.",
)
@click.option(
    "--no-live",
    is_flag=True,
    help="Use plain output instead of the live terminal view.",
)
@click.option("--cwd", default=None, help="Working directory for commands.")
@click.option(
    "--image",
    default=None,
    help="Run commands in this Docker image instead of locally.",
)
@click.option(
    "--step-limit",
    type=int,
    default=None,
    help="Maximum number of model calls.",
)
@click.option(
    "--timeout", type=int, default=None, help="Per-command timeout in seconds."
)
def run_agent(
    task,
    config_path,
    agent_name,
    model_name,
    yolo,
    output,
    no_live,
    cwd,
    image,
    step_limit,
    timeout,
):
    """Run the agent on a task. Flags override values from the YAML config."""
    try:
        config = load_config(
            config_path or DEFAULT_CONFIG_PATH, agent_name=agent_name
        )
    except (ValueError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    context = click.get_current_context(silent=True)
    if context and isinstance(context.obj, dict) and "workshop" in context.obj:
        config["workshop"] = context.obj["workshop"]
    if model_name:
        config["model"]["model_name"] = model_name
    if output:
        config["agent"]["output_path"] = output
    if step_limit is not None:
        config["agent"]["step_limit"] = step_limit
    if cwd is not None:
        config["environment"]["cwd"] = cwd
    if timeout is not None:
        config["environment"]["timeout"] = timeout
    if image:
        config["environment"]["environment_class"] = "docker"
        config["environment"]["image"] = image
        config["environment"].setdefault("cwd", "/")
    agent = build_agent(config)
    from workshop.agent.interactive import InteractiveAgent

    if (
        not no_live
        and os.name == "posix"
        and sys.stdin.isatty()
        and sys.stdout.isatty()
        and isinstance(agent, InteractiveAgent)
    ):
        from workshop.agent.live_view import AgentLiveView
        from workshop.agent.supervised import SupervisedAgent

        view = AgentLiveView(SupervisedAgent(config), task)
        outcome = view.run(inline=True)
        if outcome is None:
            raise click.ClickException(
                "Live view exited without an agent result"
            )
        if outcome.get("tool_history"):
            click.echo("Recent tools:")
            for event in outcome["tool_history"]:
                click.echo(event)
        if outcome.get("tool_count"):
            click.echo(outcome["tool_count"])
        if outcome.get("error") is not None:
            raise outcome["error"]
        result = outcome["result"]
        if view.latest_usage.startswith("[tokens]"):
            click.echo(view.latest_usage)
        if getattr(view, "latest_thinking", "") != "No model output yet":
            click.echo(view.latest_thinking)
    else:
        result = agent.run(task)
    click.echo(f"exit status: {result.get('exit_status', '')}")
    if result.get("submission"):
        Console().print(
            result["submission"], markup=False, highlight=False, soft_wrap=True
        )
    if result.get("cleanup_warning"):
        click.echo(result["cleanup_warning"], err=True)
    if output:
        click.echo(f"trajectory saved to {output}")
    if result.get("exit_status") == "UserInterruption":
        click.echo(
            "Interrupted. Changes, remote work, or cleanup may be incomplete.",
            err=True,
        )
        raise click.exceptions.Exit(130)
    if result.get("exit_status") != "Submitted":
        raise click.exceptions.Exit(1)
