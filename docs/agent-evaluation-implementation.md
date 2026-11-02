# Agent evaluation implementation tracker

This checklist tracks the work from the current evaluation foundation to a
report-only benchmark and trace-review workflow. Update it as work is completed;
check a box only when the implementation and its verification are complete.

**Safety status:** There is no benchmark runner or verified sandbox. Do not use
the broker prototype or current Docker environment to run untrusted benchmark
agents. The sandbox design in `docs/agent-evaluation-sandbox.rst` is proposed
and still needs security review. `docs/agent-evaluation-plan.md` contains the
broader design and `docs/agent-evaluation.rst` documents current APIs.

## Agreed boundaries

- [x] Keep `workshop.agent`, `workshop.agent_config`,
  `workshop.agent_benchmark`, and `workshop.agent_eval` as sibling packages.
- [x] Target rootless Podman on Linux for the initial isolation profile; do not
  treat a shared-kernel container as equivalent to a VM.
- [x] Use a host-controlled model broker. Coding and review benchmarks may use
  an explicitly selected remote provider with sanitized fixtures; trace review
  must use a locally controlled model and have no external network or MCP access.
- [x] Keep benchmark results report-only; require human review for review
  findings and proposal promotion. Do not add tool-call approvals or automatic
  prompt, skill, or suite changes.
- [x] Distinguish task failure, pending human review, and infrastructure error
  from a pass. Fail closed when required isolation cannot be verified.

## Current foundation

- [x] Add experimental versioned case, suite, trace-reference, case-result,
  and run-result contracts, with independent outcome counts.
- [x] Add explicit POSIX private JSON storage with owner-only checks, confined
  filenames, and atomic replacement. Storage does not redact or encrypt secrets.
- [x] Add read-only Podman preflight diagnostics. Readiness remains false;
  `podman info` does not prove that any isolation control is enforced.
- [x] Add an experimental text-only Unix-socket broker prototype tested with
  fake async providers, per-run credentials, bounded frames and requests, and
  basic timeout, concurrency, and shutdown handling.
- [x] Draft a threat model and rootless-container/trusted-scoring contract.
  This is a proposal, not a completed security review.
- [ ] Complete remaining record contracts and provenance: timestamps, agent,
  model and prompt identities, safe configuration fingerprints, case hashes,
  human reviews, proposals, and promotion decisions.
- [ ] Validate imported trajectories and hashes; do not assume a reference
  proves that trace contents are safe, redacted, or successful.

## 1. Runtime enforcement and disposable probes — next

A fixed trusted diagnostic now runs with the initial test limits against a
locally available, pinned Fedora image. It observes selected runtime settings
and checks cleanup, but does not establish the full sandbox boundary. The image
is not an approved benchmark image, and readiness remains false.

- [x] Add a fixed-command Podman diagnostic and tests for preflight failure,
  malformed output, timeout, and cleanup; run it once on the local runtime.
- [x] Add and locally run a second bounded diagnostic for selected network,
  host-loopback, mount, socket, tmpfs, and PID-limit observations. DNS remains
  unverified when resolution fails; these specific probes are not proof of the
  complete network or filesystem boundary.
- [x] Exercise a fixed real client timeout and verify container removal. An
  initial ``rm -f`` attempt left a container behind; it was removed manually.
  A subsequent kill-then-remove probe succeeded.
- [x] Test a known-answer UDP DNS query against a temporary host IPv4 loopback
  listener, including a host baseline and explicit inconclusive results. This
  covers only that endpoint, not general DNS or system-resolver isolation.
- [x] Test a controller crash against one explicitly identified, labelled
  disposable diagnostic container and verify exact-ID recovery. This is not
  automatic orphan discovery or production benchmark recovery.
- [x] Run a 64 MiB memory-pressure diagnostic and verify the observed cgroup
  limit, Podman OOM indication, and cleanup on the local runtime.
- [ ] Find and verify a supported inode-quota mechanism. Rootless Podman 5.8.9
  rejects the diagnostic's ``nr_inodes=128`` tmpfs option and the tested
  ``--mount type=tmpfs`` inode variants. Its documented XFS project-quota
  volume approach requires host setup outside the no-host-mount/no-elevation
  profile; this host uses Btrfs. The Podman inode check is unverified, not a
  pass. A manual rootless direct-OCI ``crun`` diagnostic did enforce a
  128-inode tmpfs (114 files before ENOSPC) when bypassing the Podman parser.
  It did not establish the other required sandbox controls. The proposed
  standalone controller design is in `docs/agent-evaluation-crun-design.md`;
  independent review and implementation remain open. Do not substitute a byte
  or memory limit for an inode limit.

- [ ] Agree on exact supported runtime and image requirements, image
  provenance, seccomp/LSM policy, filesystem quota mechanism, resource limits,
  and recovery procedures before implementation.
- [ ] Implement the reviewed rootless container lifecycle with no fallback to
  local execution or ordinary Docker. Keep benchmark execution disabled until every gate below
  is satisfied.
- [ ] Verify effective non-root identity, capabilities, seccomp/LSM, read-only
  root, network isolation, mounts, runtime-socket absence, and resource limits
  using actual disposable Podman integration probes.
- [ ] Verify CPU, memory, process, disk/inode, output, artifact, and wall-time
  limits; fail closed when controls are unavailable or cannot be verified.
- [ ] Test timeout, interruption, failed cleanup, container removal, controller
  crash, and orphan recovery; report unverifiable cleanup as infrastructure error.
- [ ] Confirm the agent and its tool subprocesses—not just individual commands—
  run inside the verified boundary. Never mount the live workspace or credentials.

## 2. Production model broker

- [ ] Define and review the production wire protocol, including native tool
  calls and results, streaming, errors, cancellation, and provider usage.
- [ ] Bind provider, model, endpoint, and credentials on the host; reject agent
  routing overrides and do not expose a general proxy or filesystem interface.
- [ ] Enforce request, response, concurrency, request-count, token, cost, and
  wall-time limits. Specify behavior when provider usage or cost is unavailable.
- [ ] Isolate provider execution so blocked or cancellation-resistant work can
  be handled; do not claim a timeout necessarily stops remote provider work.
- [ ] Verify per-run socket access, cross-run isolation, cleanup, and limit
  enforcement from actual restricted containers; test malformed and partial
  requests and sensitive-error handling.
- [ ] Connect an explicitly selected provider only after security review. Record
  that benchmark inputs can leave the host; use sanitized fixtures.
- [ ] Keep trace review disabled until a transport-level local-only model route
  is specified and verified without external network or MCP access.

## 3. Artifact transfer and trusted scoring

- [ ] Specify fixture and artifact formats, allowed paths and file types, size
  limits, hashes, and race-resistant import/export procedures.
- [ ] Reject traversal, absolute paths, links, special files, duplicates,
  collisions, oversized data, and unsupported metadata; never extract hostile
  archives into the live checkout.
- [ ] Create a separate disposable restricted scorer with no broker, network,
  credentials, private storage, or authoritative checks. Never execute
  agent-produced code on the host.
- [ ] Implement a bounded black-box interface: trusted checks remain outside
  the scorer; the program receives only the inputs needed for each test. Mark
  cases requiring unsupported scoring methods as infrastructure errors.
- [ ] Independently test check isolation, verdict integrity, malicious output,
  resource exhaustion, cleanup, and failure classification on real runtimes.
- [ ] Obtain security review of the implementation and evidence before any real
  benchmark agent or generated patch is executed.

## 4. Curated suites and report-only runner

- [ ] Create small versioned coding fixtures with independent black-box checks.
- [ ] Create review fixtures with known defects and structured findings; keep
  defect matching and false-positive judgments pending human review.
- [ ] Implement suite selection, named-agent association, disposable case
  lifecycle, private run storage, provenance, and explicit infrastructure errors.
- [ ] Record available model identity, usage, cost, timing, and artifact hashes;
  keep missing measurements unknown rather than inventing them.
- [ ] Produce per-case and aggregate reports; support repeated runs and
  comparisons against the same suite versions. Do not add CI quality gates.

## 5. Trace review and improvement lifecycle

- [ ] Import and validate supported trajectories with hashes and provenance;
  never automatically upload or commit traces.
- [ ] Enforce and test local-only trace-review model access with no external
  networking or MCP; keep trace and proposal storage explicitly private.
- [ ] Generate evidence-linked evaluation and prompt/skill/harness proposals;
  treat trace instructions and content as untrusted.
- [ ] Record human accept, reject, and revision decisions; require a separate
  explicit action to promote a reviewed case. Never apply changes automatically.
- [ ] Compare baseline and candidate configurations on new and existing suites,
  with repeated runs and honest pending/error handling.

## Verification for each slice

- [ ] Write a focused failing test, confirm the expected failure, then implement
  the smallest passing change and refactor with tests green.
- [ ] Use fake providers and executors for deterministic unit tests. Use real,
  disposable runtime integration tests to establish isolation; mocks are not
  evidence of a security boundary.
- [ ] Run relevant tests, Ruff, and documentation checks; report unavailable
  prerequisites and known limits rather than silently skipping them.
- [ ] Keep documentation and this checklist aligned with actual behavior.
