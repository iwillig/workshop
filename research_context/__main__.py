"""Read Asana tasks from the command line."""

import json
import os

import asana
import click
from asana.rest import ApiException
from dotenv import load_dotenv
from urllib3.exceptions import HTTPError

from research_context.notion import notion_commands


def tasks_api():
    token = os.environ.get("ASANA_ACCESS_TOKEN", "").strip()
    if not token:
        raise click.ClickException("Set ASANA_ACCESS_TOKEN to an Asana access token.")
    configuration = asana.Configuration()
    configuration.access_token = token
    return asana.TasksApi(asana.ApiClient(configuration))


@click.group()
def cli():
    """Research and context commands."""
    load_dotenv(dotenv_path=".env.local", override=False)


@cli.group(name="asana")
def asana_commands():
    """Read tasks from Asana."""


@asana_commands.command("list-tasks")
@click.argument("project_gid")
def list_tasks(project_gid):
    """List tasks in the Asana project PROJECT_GID as JSON."""
    try:
        tasks = tasks_api().get_tasks_for_project(
            project_gid, {"opt_fields": "gid,name,completed"}, _request_timeout=30
        )
        click.echo(json.dumps(list(tasks), indent=2))
    except ApiException as exc:
        raise click.ClickException(f"Asana request failed (HTTP {exc.status}).") from exc
    except HTTPError as exc:
        raise click.ClickException("Could not connect to Asana.") from exc


@asana_commands.command("get-task")
@click.argument("task_gid")
def get_task(task_gid):
    """Get the Asana task TASK_GID as JSON."""
    try:
        result = tasks_api().get_task(
            task_gid,
            {"opt_fields": "gid,name,notes,completed,due_on,assignee.name,permalink_url"},
            full_payload=True,
            _request_timeout=30,
        )
        click.echo(json.dumps(result["data"], indent=2))
    except ApiException as exc:
        raise click.ClickException(f"Asana request failed (HTTP {exc.status}).") from exc
    except HTTPError as exc:
        raise click.ClickException("Could not connect to Asana.") from exc


cli.add_command(notion_commands)


if __name__ == "__main__":
    cli()
