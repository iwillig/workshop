# Research and context

The research and context component provides read-only commands for listing and inspecting Asana tasks. Output is JSON.

## Setup

Install the Python dependencies with `pipenv sync`, then install the workshop command with `pipenv run pip install -e .`. Copy `.env.local.example` to `.env.local` and replace the placeholder with an Asana personal access token that can read the tasks. Load it into your shell before running commands:

```shell
set -a
source .env.local
set +a
```

Keep `.env.local` out of source control.

## Commands

Run these commands from the repository root:

```shell
pipenv run workshop research-context asana list-tasks PROJECT_GID
pipenv run workshop research-context asana get-task TASK_GID
```

The original `pipenv run python -m research_context asana` entry point also remains available.

The list command returns all tasks in the project, including completed tasks. The inspect command returns selected task details. Both commands require the corresponding Asana resource ID. Use `--help` for command usage.

Run the tests with `pipenv run python -m pytest tests/test_research_context.py`.
