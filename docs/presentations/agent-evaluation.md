---
title: "Building & Evaluating Coding Agents"
subtitle: "A practical, report-only development workflow"
date: "Workshop"
lang: en
header-includes: |
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; color: #172438; }
    div.slide { background: #f7f9fc; font-size: 120%; }
    div.slide h1, div.slide h2 { color: #123962; }
    div.slide h1 { border-bottom: 4px solid #23a39a; padding-bottom: .2em; }
    div.slide h2 { border-bottom: 4px solid #23a39a; padding-bottom: .2em; }
    div.slide li { margin: .38em 0; }
    div.slide img { max-width: 100%; max-height: 55vh; }
    div.slide code { color: #164f76; }
    div.slide pre { background: #e8eff6; border-left: 5px solid #23a39a;
                    padding: .75em; font-size: .8em; }
    div.slide blockquote { border-left: 5px solid #e6a23c; padding: .2em .8em;
                           margin-left: 0; background: #fff5e5; }
    div.slide.titlepage { background: #123962; color: #f7f9fc; }
    div.slide.titlepage h1, div.slide.titlepage p { color: #fff; }
  </style>
---

# Why build this?

- Use coding agents for more than one task: **implementation and review**.
- Make runs visible, configurable, and bounded enough for development.
- Measure changes with repeatable examples, not intuition alone.
- Keep people responsible for interpreting review findings.

> Goal: a useful development feedback loop, not an autonomous quality gate.

# The building blocks

```{.plantuml width=90% caption="Agent evaluation components"}
@startuml
left to right direction
skinparam backgroundColor transparent
skinparam shadowing false
skinparam defaultFontName SansSerif
skinparam rectangleBackgroundColor #E8EFF6
skinparam rectangleBorderColor #123962
rectangle "Agent config\n(YAML)" as config
rectangle "Agent\n(llm + tools)" as agent
rectangle "Benchmark\n(versioned cases)" as bench
rectangle "Evaluation\n(private reports)" as eval
config --> agent : configures
bench --> agent : tasks
agent --> eval : results
bench --> eval : checks
@enduml
```

Agent, configuration, benchmark, and evaluation are sibling packages.

# How an agent works

1. Load a named agent and task.
2. Send the task and available tools to the selected model.
3. Execute tool calls and return observations to the model.
4. Repeat until submission, an error, or a configured limit.

Local tools include `read`, `edit`, and `bash`; native tool calls can also use
configured MCP servers. Tool calls run without approval prompts.

# Feedback during a run

- Show model activity, tool calls, and available token usage.
- Use an inline Textual view for interactive terminal runs.
- Use plain output for non-interactive runs and benchmark reports.
- Allow the user to stop a supervised interactive run.

Stopping is best effort: partial edits or remote work may remain.

# From agent to benchmark

```{.plantuml width=85% caption="Local benchmark lifecycle"}
@startuml
skinparam backgroundColor transparent
skinparam shadowing false
skinparam defaultFontName SansSerif
skinparam sequenceParticipantBackgroundColor #E8EFF6
skinparam sequenceParticipantBorderColor #123962
actor Developer
participant Runner
participant Agent
participant Evaluator
Developer -> Runner: Choose suite + agent
Runner -> Runner: Verify and copy fixture
Runner -> Agent: Run task in workspace
Agent --> Runner: Submit result
Runner -> Evaluator: Check result
Evaluator --> Runner: Outcome
Runner --> Developer: Save private report
@enduml
```

The same suite can be run again with another agent configuration.

# Two kinds of case

**Coding cases**

- Ask for a small code change.
- Run independent, deterministic checks against the result.
- Report pass, fail, or an infrastructure error.

**Review cases**

- Ask the agent to inspect code for defects.
- Save its findings alongside the expected defect.
- Leave the result pending until a person judges it.

# Small, versioned suites

- `coding-v1` and `review-v1`: one starter case each.
- `coding-v2` and `review-v2`: three cases each, including multi-file fixtures.
- `coding-v3` and `review-v3`: six cases each.
- Case, suite, fixture, and scoring identities support repeatable comparisons.
- Hash checks detect changes to the bundled fixture and scoring files.

A versioned case makes a result understandable; it does not guarantee quality.

# A real review run

The `review-v1` case asks the agent to review a small average function.

- The documented behavior says an empty input returns zero.
- The implementation divides by the input length.
- The agent read the file and identified the empty-input division by zero.
- The run was saved as **pending human review**, not an automatic pass.

The expected finding is benchmark reference material, not the agent's answer.

# Reading the outcome

| Outcome | Meaning |
|:--|:--|
| **Pass** | Deterministic coding checks passed. |
| **Fail** | A completed coding check failed. |
| **Pending human review** | A review was submitted; a person must judge it. |
| **Infrastructure error** | The agent, provider, or evaluator could not complete. |

Unknown token or cost measurements remain unknown. Counts stay separate.

# Human judgment stays separate

1. Inspect the agent's findings and the expected defect.
2. Record **pass**, **fail**, or **inconclusive**, with a rationale.
3. View the decision history alongside the original result.

```text
workshop benchmark review RUN_ID --case CASE_ID \
  --decision pass --reviewer "Reviewer" \
  --rationale "Identified the defect" --storage /private/benchmarks
```

The original run remains unchanged. Reviewer identity is self-declared.

# Try the local review benchmark

```sh
workshop benchmark run --suite review-v1 \\
  --config examples/review-agent.yaml --agent reviewer \\
  --storage "$HOME/private-benchmarks" --local
```

- Uses the configured `reviewer` and the `review-v1` suite.
- Stores reports in `~/private-benchmarks` by default.
- Review the JSON outcome: infrastructure errors exit nonzero after the report
  is saved; quality failures and pending reviews remain report-only.
- A remote model provider may receive fixture content.

# The important safety boundary

> **Local execution is not a sandbox. Use trusted agents and fixtures only.**

- Agent tools and coding checks run with your user permissions.
- A temporary directory does not prevent access to other files or the network.
- Private reports can contain sensitive content and are not automatically redacted.
- Timeouts and cleanup are best effort; remote calls can outlast local work.

# Why not build isolation first?

We investigated rootless containers, resource limits, artifact collection, and
release handshakes. The evidence is useful, but it is **not a verified sandbox**.

For this development workflow we chose a simpler path:

- Run only trusted examples locally and make the risk explicit.
- Keep evaluation report-only and human review mandatory for findings.
- Defer strong isolation and its independent security review.

# Where this goes next

- Validate more agents and cases with real, explicitly selected models.
- Improve report readability and live streaming output.
- Expand comparisons and trace-informed proposals for human review.
- Verify a local-only trace-review boundary before using sensitive traces.
- Revisit isolation before running untrusted workloads.

# Takeaways

1. **Configurable agents** make coding and review workflows reusable.
2. **Versioned benchmarks** provide concrete development feedback.
3. **Human judgment and explicit outcomes** prevent false confidence.
4. **Local means trusted:** a working benchmark is not a security boundary.
