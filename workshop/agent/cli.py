"""Command line interface for the workshop mini coding agent."""

from pathlib import Path

import click

from workshop.agent.config import DEFAULT_CONFIG_PATH, build_agent, load_config


@click.group(name="agent")
def agent_commands():
    """Run the workshop mini coding agent (a mini-swe-agent port on the llm library)."""


@agent_commands.command(name="run")
@click.option("-t", "--task", required=True, help="The task for the agent to solve.")
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="YAML config file (default: the packaged default config).",
)
@click.option("-m", "--model", "model_name", default=None, help="An llm model id or alias (default: llm's default model).")
@click.option("-y", "--yolo", is_flag=True, help="Run commands without confirmation.")
@click.option("-o", "--output", type=click.Path(path_type=Path), default=None, help="Save the trajectory to this file.")
@click.option("--cwd", default=None, help="Working directory for commands.")
@click.option("--image", default=None, help="Run commands in this Docker image instead of locally.")
@click.option("--step-limit", type=int, default=None, help="Maximum number of model calls.")
@click.option("--timeout", type=int, default=None, help="Per-command timeout in seconds.")
def run_agent(task, config_path, model_name, yolo, output, cwd, image, step_limit, timeout):
    """Run the agent on a task. Flags override values from the YAML config."""
    config = load_config(config_path or DEFAULT_CONFIG_PATH)
    if model_name:
        config["model"]["model_name"] = model_name
    if yolo:
        config["agent"]["mode"] = "yolo"
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
    result = agent.run(task)
    click.echo(f"exit status: {result.get('exit_status', '')}")
    if result.get("submission"):
        click.echo(result["submission"])
    if output:
        click.echo(f"trajectory saved to {output}")
