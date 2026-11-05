---
title: "The AI Workshop"
subtitle: "A small-team approach to context, agents, and learning"
date: "Project introduction"
lang: en
header-includes: |
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; color: #172438; }
    div.slide { background: #f7f9fc; font-size: 118%; }
    div.slide h1, div.slide h2 { color: #123962; }
    div.slide h1, div.slide h2 { border-bottom: 4px solid #23a39a;
                                 padding-bottom: .2em; }
    div.slide li { margin: .32em 0; }
    div.slide img { max-width: 100%; max-height: 53vh; }
    div.slide code { color: #164f76; }
    div.slide pre { background: #e8eff6; border-left: 5px solid #23a39a;
                    padding: .7em; font-size: .75em; }
    div.slide blockquote { border-left: 5px solid #e6a23c; padding: .2em .8em;
                           margin-left: 0; background: #fff5e5; }
    div.slide.titlepage { background: #123962; color: #f7f9fc; }
    div.slide.titlepage h1, div.slide.titlepage p { color: #fff; }
  </style>
---

# Why a workshop?

A collection of tools for working with LLM Agents and Code bases.

# Structure

- research_context
- template_engine

- workshop/agent
- workshop/agent_config
- workshop/agent_benchmark
- workshop/agent_eval

# Agent package responsibilities

- `workshop.agent`: agent loop, models, tools, environments, and live output.
- `workshop.agent_config`: load YAML and construct named agents.
- `workshop.agent_benchmark`: versioned cases, local execution, and scoring.
- `workshop.agent_eval`: result contracts, private storage, and human reviews.

The packages have separate responsibilities, while the CLI connects them.

# The big picture

```{.plantuml width=90% caption="Conceptual workshop workflow"}
@startuml
left to right direction
skinparam backgroundColor transparent
skinparam shadowing false
skinparam defaultFontName SansSerif
skinparam rectangleBackgroundColor #E8EFF6
skinparam rectangleBorderColor #123962
rectangle "Task" as task
rectangle "Context\ncode + work items" as context
rectangle "Agent\nmodel + tools" as agent
rectangle "Result\n+ human review" as result
rectangle "Evaluation\n+ feedback" as eval
task --> context
context --> agent
agent --> result
result --> eval
eval ..> context : future learning
@enduml
```

**Conceptual:** the full feedback and learning loop is not implemented yet.

# What is available today?

- **Research and context:** read-only work-item, document, and Git commands.
- **Coding agent:** configurable `llm`-based agent with tools and live feedback.
- **Local benchmarks:** small coding and review suites with private reports.
- **Utilities:** project templates, browser screenshots, docs, and slide builds.

These are working foundations, not a finished autonomous platform.

# Explore work and context

Use one CLI to inspect relevant information:

- Asana tasks and Notion pages.
- GitHub issues, pull requests, files, and commits.
- Local Git status, diffs, and history.

```sh
workshop research-context git diff --staged
workshop research-context github get-pr OWNER/REPO 42
```

The research commands are read-only and produce JSON. Service credentials and
resource permissions are still required where applicable.

# The coding agent

- A named YAML configuration selects the model, prompts, tools, and limits.
- The agent asks an `llm` model for actions, runs tools, and returns results.
- Built-in `read`, `edit`, and `bash` tools support native tool calling;
  configured MCP servers can add tools.
- Legacy shell protocol remains available.
- Tool calls run **without per-call approval**.

Both local and Docker execution are available; neither is a hardened sandbox.

# Inside the agent

1. `agent_config` loads a named definition and builds its components.
2. `LlmModel` sends the task and maintains the model conversation.
3. `DefaultAgent` executes actions and records observations.
4. The interactive layer displays progress; the environment runs tools.
5. A submission, limit, or error ends the foreground run.

Native tool calls and the legacy fenced-shell protocol are separate modes.

# Example: one review cycle

1. A developer asks the agent to review `calculator.py`.
2. The model requests `read("calculator.py")`; the agent runs the tool.
3. The agent sends the file contents back to the model.
4. The model submits a finding with its location and impact.

The model sees the task and tool results; a remote provider may receive them.

# Example: configure a reviewer

```yaml
version: 1
agents:
  reviewer:
    model: {model_name: YOUR_LLM_MODEL, protocol: native}
    prompts:
      system: "Review code; report bugs with paths and impact."
    environment: {environment_class: local, cwd: .}
    limits: {step_limit: 12}
    tools: {read: {}}
```

This named agent exposes the built-in `read` tool. Replace `YOUR_LLM_MODEL`
with an installed, tool-capable model; configure credentials separately.

# Example: configure a coding agent

```yaml
version: 1
agents:
  coder:
    model: {model_name: YOUR_LLM_MODEL, protocol: native}
    prompts:
      system: "Make the requested change and explain the result."
    environment: {environment_class: local, cwd: ., timeout: 30}
    limits: {step_limit: 20}
    tools: {read: {}, edit: {}, bash: {}}
```

`edit` changes files and `bash` runs commands. These tools act without approval
prompts and have the user's permissions; the working directory is not a sandbox.

# Example: run a named agent

```sh
workshop agent run --agent reviewer \\
  --task 'Review calculator.py for bugs.' \\
  --cwd /path/to/disposable-workspace
```

- `--agent` selects a definition from the YAML file.
- CLI options such as `--cwd` and `--step-limit` override configuration.
- `Submitted` means the agent responded—not that its answer is correct.
- Check findings, changes, and tests before relying on the result.

# See and control a run

- Interactive POSIX terminals use an inline Textual progress view.
- Plain output supports non-interactive runs.
- Displayed usage comes from what the model reports; missing data stays unknown.
- A supervised interactive run can be stopped with Ctrl+C.
- Optional project-wide `llm` logging requires explicit configuration.

Stopping and cleanup are best effort; remote calls or partial edits may remain.

# A modular foundation

The `workshop` command brings separate components together:

- **Research and context** for finding relevant information.
- **Agent and configuration** for running tasks with a selected model and tools.
- **Benchmark and evaluation** for repeatable cases and private reports.
- **Templates and browser tools** for supporting development work.

They share an entry point, but are not yet a complete automated workflow.

# Evaluate rather than assume

- Small, versioned coding and review fixtures make runs repeatable.
- Coding cases use deterministic checks; review cases need human judgment.
- Reports distinguish **pass**, **fail**, **pending review**, and
  **infrastructure error**.
- Results and judgments go to an explicitly selected private directory.
- Results are report-only: no automatic CI quality gate.

Current v3 suites contain six coding and six review cases. They are useful
smoke tests, not broad proof of agent quality.

# How the agent system is tested

- **Deterministic tests** use fake models and executors for routine coverage.
- Agent tests cover configuration, tools, lifecycle, output, and cancellation.
- Benchmark tests cover fixture hashes, scoring, private reports, and reviews.
- Live model and benchmark tests, plus runtime diagnostics, require explicit
  opt-in. Enabled live tests require credentials and may incur provider costs.

# What the test results tell us

A recent credential-free run had **293 passing tests** and 11 opt-in checks
skipped. Two environment-specific tests passed in a separate run.

- Passing tests support confidence in the implemented behavior.
- A skipped integration test does not establish endpoint or sandbox behavior.
- One successful benchmark run does not establish overall model quality.

# A real example

A review fixture contains an average function that promises zero for an empty
input but divides by the input length.

- The configured reviewer read the fixture and identified the defect.
- The benchmark saved the finding as **pending human review**.
- A human can record a decision and rationale without changing the original run.

One successful example demonstrates the path—not general agent readiness.

# Other useful tools

**Project templates**

- Create projects from bundled or local Cookiecutter templates.
- Hooks are disabled, but templates still need to be trusted.

**Browser and documentation**

- Capture a page screenshot with headless Chrome.
- Build Sphinx documentation and Pandoc/Slidy presentations.

**Infrastructure:** a Pulumi project exists but defines no resources yet.

# What is not built yet?

- Managed background agent jobs and durable job recovery.
- An integrated task-to-agent workflow or multi-agent coordination.
- Automatic import of external traces and a verified local-only reviewer.
- A memory or learning system that carries lessons into future work.
- A verified execution boundary for untrusted agents or generated code.

Ideas and draft designs in the repository are not commitments that these
capabilities already exist.

# The learning loop we want to build

```{.plantuml width=90% caption="Proposed human-reviewed learning loop"}
@startuml
left to right direction
skinparam backgroundColor transparent
skinparam shadowing false
skinparam defaultFontName SansSerif
skinparam rectangleBackgroundColor #E8EFF6
skinparam rectangleBorderColor #123962
rectangle "Run + trace" as run
rectangle "Review\nevidence" as review
rectangle "Propose case or\nprompt improvement" as proposal
rectangle "Human\ndecision" as human
rectangle "Rerun\nbenchmarks" as eval
run --> review
review --> proposal
proposal --> human
human --> eval : if approved
eval ..> run : compare
@enduml
```

**Partly implemented:** trace capture, experimental review, and manual proposal
records exist. Verified local-only review, promotion, and reusable memory remain
open. Nothing is promoted or applied automatically.

# The next practical steps

1. Exercise and improve comparisons across agent configurations.
2. Expand cases beyond the current small fixtures.
3. Improve trace-review evidence and the human proposal workflow.
4. Consider managed jobs and stronger isolation as separate future work.

These are directions for development, not promises about delivery order.

# Safety and trust

> **The current local agent and benchmark runner are not sandboxes.**

- Agent commands and generated code can act with the user's permissions.
- Remote model providers may receive task and workspace content.
- Private logs and reports can contain sensitive data; they are not redacted.
- Use only trusted configurations and fixtures; inspect provider and tool settings.
- Trace review is not network-isolated; use synthetic or non-sensitive traces.
- Isolation prototypes and a proposed `crun` design are not security-reviewed.

# The public command groups

| Command | Purpose |
|:--|:--|
| `workshop agent` | Run a configured coding or review agent. |
| `workshop benchmark` | Run suites, inspect reports, and record reviews. |
| `workshop eval` | Experiment with trace review and proposal records. |
| `workshop research-context` | Read Asana, Notion, GitHub, and local Git. |
| `workshop template-engine` | List and create projects from local templates. |
| `workshop browser` | Capture a page screenshot. |

Use `workshop --help` or add `--help` to a command group for details.

# Explore the public CLI

```sh
workshop research-context git status
workshop research-context github --help
workshop agent run --help
workshop benchmark --help
```

Benchmark runs require an explicitly configured agent and private storage.
Local fixtures run without isolation; remote models may receive their contents.

Documentation: `readme.md`, `docs/agent.rst`, and `docs/agent-evaluation.rst`.

# Takeaways

1. **A workshop, not a factory:** practical tools for a small team.
2. **Foundations already exist:** context, agents, evaluation, and utilities.
3. **Learning is the ambition:** evidence, human review, and measured improvements.
4. **Trust boundaries matter:** today's local runner is for trusted work only.
