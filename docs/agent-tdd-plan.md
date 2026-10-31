# Configurable agents: red/green implementation plan

**Status: in progress.** This plan builds on `agent-design.md`.
Reliability work and initial named-agent configuration are implemented;
managed background jobs remain deferred.

## Decisions

- Define reusable named agents in YAML; retain existing single-agent configurations.
- Support interactive runs, non-interactive foreground runs, and managed background jobs.
- Tool calls run without human approval in every mode. Interactive mode displays progress without prompting.
- Initial tools are built-in read, edit, and Bash, using the `llm` library's tool interfaces where supported. Do not introduce arbitrary tool plugins in this release.
- Background agents must explicitly choose local or Docker execution. Managed-job storage has no default and must be supplied by configuration or invocation.

## Red/green discipline

For each slice, add the smallest observable test first and run it to
demonstrate the expected failure. Implement the smallest change that
makes that test pass, rerun it, and then refactor while keeping it
green. Repeat for each behavior listed below rather than writing an
entire phase before running tests. Run the relevant agent suite after
each slice and the broader checks before completion. Record any
failure that is unrelated to the intended assertion; it is not a valid
red result.

Use fake models, temporary directories and mocked subprocesses for
deterministic tests. Keep the existing live endpoint test as a
separate verification of real integration; it requires credentials,
network access and a running endpoint, may incur costs, and is not a
substitute for deterministic tests. Do not execute model-generated
shell commands during endpoint capability probes.

## Phase 0: resolve protocol and lifecycle details

1. Inspect the installed `llm` tool-call and tool-result APIs, including multi-call ordering, call IDs, failures, and conversation serialization. Probe the configured endpoint for native tool-call support using a harmless tool definition and no tool execution. Record observed results and limitations.
2. Present the YAML schema, tool protocol and legacy compatibility approach for approval before implementing those interfaces. A successful chat completion alone does not prove native tool support.
3. Specify the worker and restart model for managed jobs, supported operating systems, atomic persistence and locking, and behavior for actions interrupted during execution. Agree on read/edit path constraints and CLI names. A crash with an unknown write outcome must not trigger automatic replay.
4. Specify job storage permissions, secret handling, retention and deletion.

These investigation steps are not red/green implementation; use tests in subsequent phases to enforce the agreed contract.

## Phase 1: stabilize the existing agent

For each item, write a failing regression test, then fix it:

1. A malformed response from an `LlmModel` fake conversation is recorded, feedback is sent, and the next model call can recover. Repeated malformed responses reach the configured limit.
2. Existing confirmation-mode configurations fail with a clear migration message rather than silently running commands unattended.
3. Two runs on the same agent have independent call counts, cost, error counters, and wall-clock start time.
4. CLI runs return a nonzero status for non-submission outcomes and report the outcome; submission remains distinguishable from successful task verification.
5. Execution environments are cleaned up on successful completion and exceptions. Docker subprocess behavior is mocked in routine tests.

## Phase 2: named agent configuration

1. Red: select a named agent from a YAML file and assert its model, prompts, environment, tools and limits are loaded. Green: add the loader and validation incrementally.
2. Red: unknown agent, invalid fields, unknown built-in tool, conflicting prompt sources, and missing explicitly required background settings fail with actionable errors before execution. Green: add validation.
3. Red: inline and file-based prompts render correctly, with file paths relative to their YAML file. Green: connect prompt configuration.
4. Red: existing single-agent YAML and CLI invocations preserve their prior behavior. Green: add a compatibility adapter and define override precedence.

## Phase 3: built-in tools and model integration

1. Red: a native `llm` tool call arrives with its name, arguments and call ID; the agent validates it before execution and returns a matching tool result. Green: implement the adapter using the agreed protocol.
2. Red: read handles valid ranges and missing files; edit handles one exact match and rejects zero or multiple matches without changing the file. Green: implement each tool and its schema.
3. Red: Bash receives the configured environment and timeout, captures failures and bounds returned output. Green: integrate existing execution behavior.
4. Red: disabled tools, invalid arguments and failed tools produce structured results without unintended side effects. Green: validate and route failures.
5. Red: legacy fenced-shell configurations retain their documented behavior. Green: implement the agreed compatibility path.
6. Red: native batches preserve call IDs and result order while honoring the scheduler's per-tool parallel settings and serial barriers. Green: connect native actions to the scheduler and test failure and interruption handling.
7. Red: configured MCP servers expose namespaced tools and built-in resource/prompt access through the same native tool interface, with server errors and session cleanup handled correctly. Green: integrate MCP connections and adapters into the agent lifecycle. Support stdio and Streamable HTTP; use trusted server configurations only. Verify both transports with real servers and test multi-server name collisions.

## Phase 4: interactive and foreground execution

1. Red: interactive execution displays progress and runs enabled tools without prompting. Green: implement unattended execution.
2. Red: non-interactive foreground execution does not prompt and reports its result and exit status. Green: implement foreground mode.

## Phase 5: managed jobs and recovery

Implement after the worker, storage and recovery decisions are approved.

1. Red: starting a job without an explicit storage location or environment fails; a valid start returns an ID and can be inspected. Green: implement persistent job creation and status.
2. Red: enabled tool calls run without human approval. Green: implement unattended job execution.
3. Red: concurrent workers cannot execute an action twice. Green: add locking and atomic state transitions.
4. Red: a worker interrupted during a potentially changing operation is marked as having an uncertain outcome and is not automatically replayed. Green: add recovery handling.
5. Red: job completion, failure, cancellation and inspection retain the agreed status, output and exit semantics. Green: implement the remaining lifecycle.

## Phase 6: documentation and acceptance

Write a user guide with real configuration and CLI examples, prompt and model setup, interactive and background operation, job storage, cleanup, and safety limitations. Ensure documented examples are exercised by tests where practical.

Acceptance requires all deterministic agent tests and relevant full-suite checks to pass; lint, formatting and Sphinx builds must pass; and the live endpoint test should be run when credentials and service are available. Report any unavailable verification or unrelated pre-existing test failures explicitly. No claim of hardened isolation should be made for local or default Docker execution.
