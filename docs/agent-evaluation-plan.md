# Agent evaluation and learning loop: implementation plan

**Status: broader proposal, partly superseded.** A report-only local runner
for trusted fixtures is available; see `docs/agent-evaluation.rst`. The user
chose to defer the sandbox-first requirement for local development. The
isolation and trace-review requirements below remain proposals for untrusted
execution and later work, not descriptions of the local runner.

## Goal

Build an end-to-end, report-only loop that uses agent traces to propose evaluation cases and improvements to prompts or skills. Evaluate candidates against versioned benchmark suites, compare results, and allow a person to review and promote useful artifacts. Support regression detection, configuration comparisons, and readiness assessment without treating a single run or score as proof of readiness.

## Decisions

- Start with both coding and code-review agents and small curated repository fixtures.
- Keep `workshop.agent_eval` and `workshop.agent_benchmark` independently usable where practical; the existing `workshop.agent` remains the LLM-based runtime and `workshop.agent_config` loads agent definitions.
- Run benchmarks in report-only mode initially; do not introduce CI quality gates.
- A review agent proposes evaluation cases and prompt or skill improvements. A person reviews and explicitly promotes proposals. Improvements remain proposals; applying them is a separate explicit step.
- Coding cases use independent checks. Review cases require structured findings; a person judges defect matches and false positives. Do not introduce an LLM judge in the first release.
- Version suite definitions, fixture inputs, and scoring rules in the repository. Require an explicit private storage location for run records, traces, reviews, and reports; no implicit repository storage.
- A named agent may reference suite IDs; the runner can also select a suite explicitly for comparisons.
- Preserve separate pass, fail, pending-human-review, and infrastructure-error outcomes. Pending and infrastructure failures are never silently counted as passes.
- For benchmark execution, run the agent in a restricted container and keep authoritative checks outside its environment. If the required isolation cannot be established, fail closed.
- Trace review uses a locally controlled model, with the reviewer isolated from external networking and MCP access. Raw traces remain private; do not send them to remote model providers.

## Boundaries and data contracts

Design and version serializable contracts before implementing a runner. Use plain data and injectable interfaces so importing the eval or benchmark modules does not start an agent, container, or model.

- **Trace reference:** identifier and format/version, source and content hash, storage reference, and redaction/provenance metadata. Existing `mini-swe-agent-1.1` JSON trajectories are an input; validate them, not assume they prove success.
- **Trace-review proposal:** trace reference, supporting evidence, reviewer/model identity and version, observation, rationale, candidate eval and/or prompt/skill/harness suggestion, and review state. Treat trace content as untrusted input. Preserve source linkage without copying secrets into suite files.
- **Evaluation case:** stable ID and version, role, task, fixture reference/hash, constraints, scoring method/version, and expected output or independent checks. Keep agent-visible task data separate from hidden evaluator materials.
- **Suite:** stable ID and version, case references, role, and execution/scoring requirements. Definitions are shareable across agents.
- **Run and case result:** run ID, suite/case versions and hashes, agent/config/prompt/model identities where available, timestamps, duration, usage/cost if reported, artifacts, status, and diagnostic details. Distinguish task failure from endpoint, container, or evaluator failure; do not invent missing cost or usage.
- **Human review and promotion:** reviewer identity, decision, rationale, timestamp, and references to the exact reviewed proposal and version. Promotion is explicit and auditable; proposals never modify prompts, skills, or benchmark suites by themselves.

Define how to fingerprint configuration without recording credential values. Ensure paths in records cannot escape the specified storage directory. Publish actual file/CLI schemas before committing to long-term compatibility.

## Isolation and trusted evaluation

The earlier proposed profile targets rootless Podman on Linux with a trusted model broker and black-box trusted scoring; see `agent-evaluation-sandbox.rst`. A standalone rootless crun alternative is proposed in `agent-evaluation-crun-design.md` after an inode-quota feasibility test. Neither design is approved or implemented; security review and local-only trace-review transport enforcement remain blockers.

The current Docker execution environment is **not** a hardened sandbox. Do not treat a separate directory, a separate same-user process, or ordinary Docker defaults as a security boundary.

1. Establish and document a threat model and a testable sandbox contract before implementing real benchmark execution. At minimum, the agent must not receive authoritative checks, host workspace mounts, host credentials, a container runtime socket, or unnecessary network access. Apply resource and time limits and clean up on success, failure, timeout, and interruption.
2. Provision a fresh disposable fixture for each case and run. Execute the agent only inside the restricted environment. Export only the intended artifacts for scoring; treat all exported paths and content as untrusted.
3. Run authoritative checks in a separate trusted evaluator after the agent stops. Checks and expected findings must be outside the agent's accessible environment. Ensure agent-produced code cannot gain access to checks through the scoring process; validate the evaluator design and artifact handling, not just mount paths.
4. Fail closed if required sandbox features are unavailable or verification fails. A local-only fake executor may be used for deterministic framework tests but must not be presented as secure benchmark execution.
5. For trace review, require a locally controlled model and prevent the review agent from reaching external networks or MCP servers. Specify a narrowly scoped local model connection without granting general network access; a loopback URL by itself is not proof of isolation. Keep raw and proposed artifacts in explicit private storage. Local processing does not make sensitive traces harmless: restrict access, avoid unnecessary copying, and warn about secrets.
6. Specify image provenance, supported runtimes and operating systems, network/model connectivity, permissions, storage retention/deletion, and cleanup/recovery. Validate these implementation choices before claiming the sandbox is safe.

## Evaluation and benchmark workflow

1. Load a named agent and explicitly selected suite, or use its configured suite references. Allow the same suite to be run against multiple agent definitions. Reject unknown suite IDs and ambiguous selections.
2. Validate the suite version and fixture/check hashes. Create an isolated case workspace; do not place private run storage or scoring checks where the agent can access them.
3. Run the agent with configured limits and save a trace to private run storage. Record model identity and actual available usage, cost, and timing.
4. Collect the intended output or patch; run the trusted evaluator. Coding cases receive deterministic check results. Review cases receive schema and unchanged-workspace checks, then remain **pending human review** for matching known defects and false positives.
5. Produce a report with per-case results and aggregate counts. Keep pending, infrastructure errors, and unavailable measurements explicit; do not convert them into passing scores. Support repeated runs and record per-run variation.
6. Review a stored trace with a local isolated review agent. Generate candidate eval and prompt/skill improvement records, preserving source references and evidence. A person can accept, reject, or request changes.
7. On explicit promotion, write or import reviewed candidate cases into a version-controlled suite through a separate user-directed action. Keep prompt and skill proposals as artifacts; do not apply them automatically. The skill subsystem does not yet exist, so skill proposals are descriptive records only.
8. Compare the original and candidate agent configurations on both the new case and existing suite versions. Report outcomes and evidence; adoption of improvements remains a separate decision.

## CLI and integration sketch

Exact command names and schemas are proposed, not yet implemented:

```text
workshop benchmark run --agent-config agents.yaml --agent coder --suite coding-v1 --storage /private/runs
workshop benchmark report RUN_ID --storage /private/runs
workshop eval review-trace TRACE_ID --reviewer local-reviewer --storage /private/runs
workshop eval inspect PROPOSAL_ID --storage /private/runs
workshop eval decide PROPOSAL_ID --decision accept --storage /private/runs
```

A named agent may contain `benchmarks: [coding-v1]`. Explicit suite selection must permit comparisons across agents. Extend configuration validation without breaking legacy single-agent YAML. A decision on a proposal is not permission to execute a tool, and this plan does not reintroduce agent tool-call approvals.

## Red/green delivery plan

For every slice, write a focused failing test first, verify the failure is for the intended behavior, implement the smallest passing change, and refactor with tests green. Use fake model and executor interfaces for deterministic unit tests. Add integration tests for actual isolation rather than assuming mocks prove it.

### Phase 1: contracts and private storage

1. Test valid and invalid versioned cases, suites, trace references, proposals, reviews, and run results; implement independent data contracts.
2. Test explicit storage selection, path confinement, restrictive permissions where supported, atomic writes, and absence of deliberately persisted credential values.
3. Test run status aggregation, especially pending human review and infrastructure failures. No quality gate is created.

### Phase 2: sandbox and trusted scoring

1. Write a threat model and restricted-container specification, including the review model connectivity boundary. Obtain review of these security choices before implementation.
2. Test fail-closed startup when isolation is unavailable; implement the sandbox adapter and cleanup.
3. Test that agent-visible fixtures exclude hidden checks and private storage, and that checks cannot be modified through the agent environment. Test untrusted artifact paths, resource exhaustion, timeouts, and interrupted runs. Use independent verification; do not run dangerous probes against a real workspace.
4. Test trusted scoring on exported artifacts without exposing authoritative checks to agent-controlled code. Record infrastructure errors separately.

### Phase 3: curated cases and report-only runner

1. Add small coding and review fixtures with separately stored authoritative tests and expected findings. Version and hash all artifacts.
2. Test fixture copying, named-agent and suite selection, CLI overrides, case lifecycle, and explicit storage. Extend agent YAML with suite references while retaining legacy files.
3. Test coding checks, review output schema and unchanged-workspace checks; record review matching as pending until a person scores it.
4. Test repeated runs, model/tool failure, timeout, missing usage, report serialization, and comparisons across identical suite versions. Implement report-only CLI and APIs.

### Phase 4: trace review and candidate lifecycle

1. Test importing and validating existing trajectories, recording references, and rejecting unsafe paths. Never automatically upload or commit a trace.
2. Test that the review environment rejects remote models, external network, and MCP access; verify a local model path works without opening general network access.
3. Test generated candidate records and provenance, including malformed proposals and untrusted trace instructions. No automatic promotion or file modification.
4. Test human accept/reject/revision decisions and audit records; implement explicit promotion of a reviewed case as a separate action. Prompt and skill proposals remain unapplied.
5. Test comparison of baseline and candidate configurations on new and existing cases with repeated runs and honest pending/error handling.

### Phase 5: documentation and verification

Document suite creation, agent associations, sandbox requirements, local trace review, private storage, human scoring, promotion, comparisons, retention, limitations, and example commands. Test the documented examples and build Sphinx. Run deterministic tests and integration tests, report-only benchmark examples, lint, and the full suite where possible. Live model or sandbox tests must report unavailable prerequisites explicitly rather than silently passing.

## Remaining design decisions

- Exact rootless Podman enforcement and broker protocol, especially allowing only the local model endpoint for trace review without external network access.
- How trusted scoring runs agent-produced code without exposing hidden checks or allowing the code to tamper with the scoring environment.
- Exact case schemas and the structured review format, including how human judgments are recorded.
- CLI names, suite IDs/versioning, private storage permissions, retention, and deletion.
- Supported model adapters for verifying local-only trace review and the provenance of prompt/model versions.
- Whether report-only benchmark commands return nonzero for infrastructure/configuration errors; quality outcomes themselves must not become CI gates by default.
