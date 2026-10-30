# Research and context

The research and context component provides read-only commands for Asana tasks and Notion pages. Output is JSON.

## Setup

Install the Python dependencies with `pipenv sync`, then install the workshop command with `pipenv run pip install -e .` and activate the environment with `pipenv shell`. Copy `.env.local.example` to `.env.local` and replace the placeholders with an Asana personal access token and a Notion integration token. Each token needs access to the resources it reads. The commands load `.env.local` from the current working directory automatically; existing environment variables take precedence.

Keep `.env.local` out of source control.

## Commands

Run these commands from the repository root:

```shell
workshop research-context asana list-tasks PROJECT_GID
workshop research-context asana get-task TASK_GID
workshop research-context notion search-pages "QUERY"
workshop research-context notion get-page PAGE_ID
```

The original `pipenv run python -m research_context asana` entry point also remains available.

The list command returns all tasks in the project, including completed tasks. The inspect command returns selected task details. Both commands require the corresponding Asana resource ID. Use `--help` for command usage.

The Notion search command matches page titles; the page command retrieves metadata and nested content blocks. See the Sphinx command reference for details.

Run the tests with `pipenv run python -m pytest tests`.
