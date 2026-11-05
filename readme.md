# Workshop

A collection of tools to make working with the LLM Agents easier.

## Why a workshop?

The workshop is a riff on the idea of an AI factory. Factories suggest
large, complicated assembly lines that take thousands of people to
manage and run.

We're a team of four, so we need something smaller and more focused: a
workshop. It is designed to run on a person's own machine or in the
cloud, giving them control over the process, and to support much
smaller teams. It has
benches, tools, and a shared understanding of how we build together.
It's not an assembly line designed to produce thousands of pull
requests per day.

## The workshop as a viable system

The [Viable System Model](https://en.wikipedia.org/wiki/Viable_system_model)
(VSM) describes how the engineer, agents, tools, and feedback work together.
The engineer running the workshop directs its work and is accountable for the
results. Some capabilities in this model are still planned.

- **System 1, operations:** The engineer and agents do the work, such as
  research, coding, and pull request review.
- **System 2, coordination:** Conventions, task boundaries, shared context,
  limits, and handoffs help activities work together without conflict.
- **System 3, operational management:** The engineer selects work, configures
  agents and resources, monitors runs, and intervenes when needed.
- **System 3\*, assurance:** The engineer checks results using tests, traces,
  direct inspection, and reviews.
- **System 4, intelligence and adaptation:** LLMs help explore possibilities,
  interpret evidence, and propose improvements. The engineer brings context,
  judgment, and review.
- **System 5, identity and policy:** The engineer sets the workshop's purpose,
  acceptable risks, and priorities, balancing present work with improvement.

The engineer moves between these functions throughout the work. Reviewing a
pull request finding provides assurance. Spotting a pattern of missed defects
can lead to a better review approach. LLMs can help with both; the engineer
makes the decisions.

## Anatomy of an AI factory

An AI factory brings together models, context, tools, workflows, and
feedback to produce useful work repeatedly. The workshop uses the same
ideas at a scale suited to a small team. These are conceptual building
blocks, not a claim that every capability is implemented here.

- **Work intake:** Capture a task, its constraints, and what success looks like.
- **Models and inference:** Run AI models and choose which model to use for a task.
- **Context and knowledge:** Supply instructions, documents, code, retrieved information, and relevant memory.
- **Tools and execution:** Let agents search, run code, call APIs, and create artifacts within appropriate permissions and safeguards.
- **Orchestration:** Coordinate workflow steps, agents, failures, and decisions that need human input.
- **Human oversight:** Review results and approve actions where human judgment or accountability is needed.
- **Observation and evaluation:** Use logs, traces, tests, and feedback to understand behavior and assess results.
- **Governance and operations:** Manage security, privacy, access, cost, reliability, and deployment across the system.

A typical workflow moves from a task through context gathering and
execution to a result and human review. Traces and evaluations provide
feedback for improving that workflow.

## Memory and learning

The workshop aims to include a Hermes-like memory and learning
system. Its goal is to create a feedback loop that helps the harness
learn from mistakes: capture useful lessons from execution,
evaluation, and human review, then make those lessons available for
future work. The design and implementation of this system remain to be
defined.

## Components

- [Research and context](research_context/readme.md) provides read-only Asana,
  Notion, GitHub, and local Git commands.
- The [coding agent](docs/agent.rst) runs tasks with a configured LLM model and
  tools, without tool-call approvals.
- [Agent evaluation](docs/agent-evaluation.rst) provides trusted-local,
  report-only benchmarks, comparisons, optional trace capture, and human review
  records. Its trace-review commands are experimental and not network-isolated.
- The [template engine](template_engine/readme.md) creates projects from
  trusted local templates, and the browser command captures screenshots.

The broader ideas—work intake, coordinated agent roles, reusable memory,
trace-driven improvement, and stronger isolation—remain future work or
proposals. Current prototypes do not provide a verified security boundary.

## Coding agent

See the [agent guide](docs/agent.rst) for setup, usage, and execution risks.
The agent and configuration are separate packages. Local commands and
benchmark checks run with your user permissions and are not sandboxed. A remote
model or configured MCP server may receive workspace data. Review the execution
risks and use trusted configurations and fixtures.

## Project templates

Use the [template engine](template_engine/readme.md) to generate projects from bundled or local Cookiecutter templates.

## Testing

Install development dependencies with `pipenv sync --dev` and run tests with
`pipenv run python -m pytest tests`. Live model and benchmark tests require
explicit opt-in; see the [agent guide](docs/agent.rst) and
[agent evaluation guide](docs/agent-evaluation.rst). Property-based tests use the beta
[Hegel Python library](https://github.com/hegeldev/hegel/tree/main/frontends/python),
installed as `hegeltest` and imported as `hegel`. See
`tests/test_github_properties.py` for an example. To report coverage for the
workshop packages, run `pipenv run python -m pytest tests --cov
--cov-report=term-missing`. GitHub Actions runs the same coverage report.

If a local `.env.local` contains service credentials, disable dotenv loading for
the regular test run and execute the dotenv-specific tests separately:

```shell
PYTHON_DOTENV_DISABLED=1 pipenv run python -m pytest tests \\
  --ignore=tests/test_env_local.py
pipenv run python -m pytest tests/test_env_local.py
```

This prevents missing-credential tests from picking up local tokens. It does not
unset credentials already exported in the shell.

Run the same lint and formatting checks used in GitHub Actions with
`pipenv run ruff check . --config pyproject.toml` and
`pipenv run ruff format --check . --config pyproject.toml`. Use
`pipenv run ruff format . --config pyproject.toml` to format the code.

## Browser screenshots

Capture a page's visible viewport with headless Chrome:

```shell
workshop browser screenshot https://example.com screenshot.png
```

See the [command reference](docs/workshop-cli.rst) for browser requirements and limitations.

## Infrastructure

The resource-free [Pulumi Python project](infra/readme.md) is ready for infrastructure definitions.

## Documentation

See [docs/readme.md](docs/readme.md) for instructions to build the
Sphinx documentation, including the workshop command reference.

## Install

Once published, install the Python package with Python 3.15 or newer:

```shell
python -m pip install llm-workshop
```

The installed command is `workshop`. Configure your project using
[workshop.yaml](docs/project-configuration.md). Publishing setup is described
in [docs/publishing.md](docs/publishing.md). For development, install the
Homebrew dependencies with `just install` and follow the
[component setup](research_context/readme.md).
