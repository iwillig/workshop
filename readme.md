# Workshop

A collection of tools to make working with the Common codebase easier.

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

Research and context is the first component. It provides read-only
Asana task, Notion page, GitHub issue and pull request, and local Git review commands; see [its
documentation](research_context/readme.md). The [coding agent](docs/agent.rst)
can run tasks with an LLM model without tool-call approvals. The ideas
below describe additional capabilities, not implemented features.

- Prompt builder
  - Review different models output
- Planning documents.
- Knowledge bases
  - Memory and learning from mistakes
- Agent harness
  - Agents as workers (foreman, technician, inspector)
  - Agents as tools (bandsaw, drill press, 3D printer)
- LLM interface engine
- LLM observation
- Human reviews
- Demo LLMs.
- Eval System
- Traces.

## Coding agent

See the [agent guide](docs/agent.rst) for setup, usage, and execution risks.
The agent and configuration are separate packages. The benchmark and evaluation
packages provide report-only local suites and private human-review records; see
[agent evaluation](docs/agent-evaluation.rst). Local commands and benchmark
checks run with your user permissions and are not sandboxed.

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

Install the Homebrew dependencies with `just install`. To install the
Python dependencies and use the research and context commands, follow
the [component setup](research_context/readme.md).
