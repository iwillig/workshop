# Common AI agent workshop

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

An AI factory brings together models, context, tools, workflows, and feedback to produce useful work repeatedly. The workshop uses the same ideas at a scale suited to a small team. These are conceptual building blocks, not a claim that every capability is implemented here.

- **Work intake:** Capture a task, its constraints, and what success looks like.
- **Models and inference:** Run AI models and choose which model to use for a task.
- **Context and knowledge:** Supply instructions, documents, code, retrieved information, and relevant memory.
- **Tools and execution:** Let agents search, run code, call APIs, and create artifacts within appropriate permissions and safeguards.
- **Orchestration:** Coordinate workflow steps, agents, failures, and decisions that need human input.
- **Human oversight:** Review results and approve actions where human judgment or accountability is needed.
- **Observation and evaluation:** Use logs, traces, tests, and feedback to understand behavior and assess results.
- **Governance and operations:** Manage security, privacy, access, cost, reliability, and deployment across the system.

A typical workflow moves from a task through context gathering and execution to a result and human review. Traces and evaluations provide feedback for improving that workflow.

## Memory and learning

The workshop aims to include a Hermes-like memory and learning system. Its goal is to create a feedback loop that helps the harness learn from mistakes: capture useful lessons from execution, evaluation, and human review, then make those lessons available for future work. The design and implementation of this system remain to be defined.

## Components

Research and context is the first component. It provides read-only Asana task and Notion page commands; see [its documentation](research_context/readme.md). The other components below are ideas, not implemented features.

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

## Documentation

See [docs/readme.md](docs/readme.md) for instructions to build the Sphinx documentation, including the workshop command reference.

## Install

Install the Homebrew dependencies with `just install`. To install the Python dependencies and use the research and context commands, follow the [component setup](research_context/readme.md).
