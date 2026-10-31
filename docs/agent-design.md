# Configurable coding agents: proposed design

**Status: draft for review.** This document proposes an implementation; it does not describe features that are already available.

## Goal

Define reusable agents in YAML and run a named agent interactively or as a background coding job. The modes share the same agent loop, tools, model integration, and run record.

## Decisions from the interview

- Support both a non-interactive foreground CLI and managed background jobs.
- Tool calls run without human approval in all modes. Interactive mode displays progress but does not pause for tool confirmation.
- The initial release supports built-in tools only: read, edit, and Bash.
- Keep the current single-agent YAML format working.
- Every background agent explicitly selects its execution environment. Local and Docker execution are allowed; neither is a hardened sandbox.
- There is no default managed-job storage location. Users must configure or supply one.

## Agent configuration

A YAML file can define multiple named agents. The schema below is illustrative, not final:

```yaml
agents:
  coding:
    model:
      model_class: llm
      model_name: example-model
    prompts:
      system_file: prompts/coding.md
    environment:
      environment_class: local
      cwd: /path/to/workspace
    tools:
      read: {}
      edit: {}
      bash:
        timeout: 30
    limits:
      step_limit: 50
      wall_time_limit_seconds: 900
    jobs:
      storage: /path/to/private/job-storage
```

Configuration should also cover model options, inline prompts, output limits, cost limits, and trajectory settings. Paths to prompt files are relative to the configuration file. Credentials come from environment variables or the model provider's credential mechanism, not YAML. Validate unknown tools, invalid policies, conflicting prompt sources, and missing required values before starting a run.

Load existing single-agent YAML through a compatibility adapter. Do not silently change the behavior of an existing configuration; specify migration and precedence rules before implementation.

## Tool integration

Use `llm`'s native tool interfaces where supported. The installed library exposes `Tool` with a name, description, input schema and optional implementation, `ToolCall` with arguments and an optional call ID, and `ToolResult`. Its conversation prompt accepts tools and tool results. Investigate the response and conversation APIs and test the actual Hugging Face endpoint before finalizing the integration.

The agent must inspect and validate each tool call before execution, without requesting human approval. Preserve call IDs and return results in the form expected by `llm`. Tool schemas and descriptions must reflect the actual implementation and configured permissions. Verify the endpoint's native tool-calling support; its OpenAI-compatible chat API alone does not establish that support.

Initial tools:

- **read:** read a file with optional line ranges and bounded output.
- **edit:** exact text replacement; fail if the old text is missing or occurs more than once.
- **bash:** execute a shell command in the selected environment, with a timeout and bounded returned output.

Maintain the existing fenced-shell protocol for legacy configurations, either through an adapter or an explicitly selected compatibility mode. How native tool calls and legacy commands coexist is an open design question pending endpoint testing.

## Run modes

- **Interactive:** stream progress and results to the terminal without tool-call prompts.
- **Non-interactive foreground:** run without terminal interaction.
- **Managed background:** start a job and return a job identifier. CLI commands inspect its state and results and explicitly resume recoverable interrupted jobs.

Illustrative CLI, subject to review:

```shell
workshop agent run --config agents.yaml --agent coding --task 'Review this project'
workshop agent run --config agents.yaml --agent coding --non-interactive --task 'Review this project'
workshop agent start --config agents.yaml --agent coding --task 'Fix the tests'
workshop agent jobs --storage /path/to/private/job-storage
workshop agent inspect JOB_ID --storage /path/to/private/job-storage
workshop agent resume JOB_ID --storage /path/to/private/job-storage
```

The exact CLI remains subject to implementation.

## Persistence and safety

Job records need task and configuration snapshots, conversation and tool-call state, status, timestamps, results and errors. Store them only at the explicitly selected location, with restrictive permissions where supported. They may contain sensitive data; never persist credentials deliberately. Define retention and deletion behavior before release.

Specify atomic state updates, locking and recovery from interrupted workers. A crash during a tool operation can leave its outcome unknown; do not blindly replay potentially changing actions. Resume must prevent duplicate workers executing the same action.

Local shell commands inherit user permissions and may access or modify files outside the workspace. Docker defaults are not hardened isolation. Read/edit path checks cannot constrain Bash. Document these boundaries and do not claim sandboxing.

## Reliability and verification

1. Fix malformed-response recovery, run-state reset, exit codes and deterministic environment cleanup, with regression tests.
2. Test agent definitions, validation, prompt files, legacy configuration and CLI overrides.
3. Test tool input validation, exact-match edits, failures, unattended execution, and bounded output.
4. Test foreground and managed job lifecycle, interrupted workers, concurrent resumes and recovery.
5. Use deterministic model tests for routine coverage and keep the live Hugging Face model test for endpoint compatibility. The live test needs credentials, network access and an available endpoint and may incur cost.
6. Document configuration, modes, safety, troubleshooting and job lifecycle in a user guide.

## Proposed phases

1. Investigate `llm` native tool calls and endpoint capabilities; finalize schema and CLI.
2. Fix core reliability issues and establish regression tests.
3. Add named definitions and compatible loading.
4. Add built-in native tools and legacy protocol compatibility.
5. Add managed jobs and durable recovery.
6. Complete documentation and end-to-end verification.

## Open decisions for review

- What model of worker lifetime and restart should managed jobs use on the target operating systems?
- Which workspace and file-access constraints are required for read and edit?
- What are the final YAML schema, CLI names, storage layout, retention policy and supported operating systems?
- Does the Hugging Face endpoint support native `llm` tool calls, including multiple calls and tool results?
