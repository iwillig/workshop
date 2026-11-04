# Plan to finish the evaluation foundation and start benchmarking

**Status: sandbox-first proposal, deferred for local development.** A separate
report-only local runner now supports trusted fixtures without isolation; see
`docs/agent-evaluation.rst`. This plan still describes proposed work for a
stronger boundary and does not authorize untrusted benchmark execution.
This plan narrows `agent-evaluation-implementation.md` to the first safe,
report-only benchmark. The detailed threat model and proposed standalone OCI
controller are in `agent-evaluation-sandbox.rst` and
`agent-evaluation-crun-design.md`. Update the implementation tracker as each
slice is actually verified; this plan does not supersede its safety gates.

## Current status

- **Available for trusted local development:** versioned coding/review suites,
  report-only execution, private JSON storage, comparisons, optional trace
  capture, human decisions, and experimental trace-review/proposal commands.
  Local execution is not isolated, trace review is not network-isolated, and
  storage does not redact secrets.
- **Diagnostics, not a sandbox:** Podman capability and disposable-boundary
  probes; a single-container crash-recovery diagnostic; a fake-provider,
  text-only broker; a controlled loopback DNS diagnostic; and a user-systemd
  service limit/freeze diagnostic. None enables benchmark execution.
- **Feasibility only:** a one-off direct rootless `crun` OCI bundle enforced a
  tmpfs inode limit. It did not verify the complete isolation policy. A fixed
  user-service diagnostic created a delegated child cgroup, read back limits,
  and observed service and sleep-descendant freeze/thaw and cleanup. Hostile
  descendants and standalone `crun` integration remain unverified.
- **Not implemented:** the standalone `crun` controller, production broker,
  safe artifact export, isolated scorer, isolated benchmark runner, verified
  local-only trace review, and promotion loop. There has been no independent
  security review. The trusted-local runner and manual human decisions are not
  substitutes for these boundaries.

The original plan is broad and mixes several milestones. The milestones below
apply to a future isolated runner; they are not prerequisites for the existing
trusted-local runner. Trace-driven prompt or skill promotion remains later work. Preserve existing user decisions: no tool-call approvals, explicit
private storage, no CI quality gates, and human judgment for review findings.

## Milestone 0 — agree on the first supported profile

- [x] Choose standalone rootless `crun` on Linux with a trusted host-side
  broker and no automatic fallback as the intended first boundary. The user
  accepts shared-kernel risk only after the required verification and independent
  security review; the design is not independently approved.
- [ ] Specify supported runtime/kernel versions, user namespace mappings,
  image provenance and digest policy, seccomp and LSM requirements, cgroup
  delegation, writable mounts, and concrete limits. Decide how the controller
  handles unavailable token/cost data without inventing it.
- [ ] Resolve the verifier/release handshake, tmpfs workspace lifetime and
  quiesced export, ledger ownership and recovery, and broker socket access.
  Review these choices before implementation. The agent may not supply policy.
- [ ] Define the first scoring boundary: coding cases use a narrow black-box
  protocol, and review findings remain pending human review. Cases that cannot
  be scored under this boundary are unsupported, not silently passed.

**Exit:** a reviewed, testable policy with explicit unsupported conditions;
no claim of a verified sandbox. Obtain independent security input early rather
than waiting until the runner is finished.

## Milestone 1 — prove the critical mechanics without agents

- [ ] With explicit permission, use fixed trusted diagnostics to create and
  control a dedicated delegated child cgroup, apply/read back CPU, memory,
  swap and PID limits, freeze/thaw descendants, and clean up. Check ownership,
  inheritance and attempts to modify or leave the cgroup. A local fixed-service
  diagnostic has demonstrated child CPU/memory/zero-swap/PID settings, service
  and fixed sleep descendant membership at populated freeze/thaw checkpoints,
  and cleanup. It did not test hostile descendants or standalone `crun`
  integration.
- [ ] Turn the manual `crun` inode experiment into a reproducible disposable
  test, then test all required writable mounts with byte and inode limits.
- [ ] Prove a namespace-holding workload can be quiesced and its tmpfs output
  safely inspected before teardown. An opt-in rootless `crun` test has read one
  fixed synthetic file through the frozen init's `/proc` root and verified
  cleanup; general traversal, hostile mutation, and full isolation remain
  unverified. Test unsupported kernel/permission paths; do not use the live
  checkout or real credentials.
- [ ] Prototype the trusted verifier/release handshake with fixed programs and
  adversarial substitutions. A local pipe experiment and an opt-in rootless
  `crun` fixed-program test cover denial, simulated approval/mismatch, forged
  output, invalid input, and descriptor closure. They do not authenticate a
  production verifier or test actual process substitution. Test real process
  identity, cgroup/namespace binding, race resistance and failed or incomplete
  verification; never release a real agent here.
- [ ] Test controller interruption, crash and orphan reconciliation for only
  explicitly owned resources, including ambiguous ownership and cleanup failure.

**Exit:** repeatable integration evidence for each selected mechanism; missing
prerequisites and inconclusive observations remain blockers. Existing Podman
probes or successful mocked tests are not evidence for the `crun` profile.

## Milestone 2 — build the fail-closed execution boundary

- [ ] Implement the `crun` adapter, private run ledger, pinned image/fixture
  preparation, verifier/release protocol, cgroup enforcement, deadlines, and
  ownership-based cleanup. Start with fake adapters and red/green unit tests.
- [ ] Add real disposable-runtime integration tests for non-root identity,
  capabilities, seccomp/LSM, namespaces, mounts, network, limits, cancellation,
  crash recovery and failure of every required control.
- [ ] Implement quiesced, bounded artifact collection with no-follow/beneath
  traversal, regular-file and link checks, duplicate/collision detection, and
  separate private staging. Do not execute exported files on the host.
- [ ] Verify the implementation against the security review and fix findings.
  Keep benchmark agent execution disabled until the review and runtime tests
  explicitly accept the boundary.

**Exit:** a reviewed and independently tested execution boundary with verified
cleanup; unavailable enforcement fails closed with an infrastructure error.
This is not a guarantee against kernel/runtime escape or a hostile host user.

## Milestone 3 — broker and independent scoring

- [ ] Specify and implement the production broker protocol: host-selected
  model/provider, native tool calls/results, bounded messages and streaming,
  authentication, cancellation, and request/token/cost/time/concurrency
  limits. Keep credentials out of the workload; handle unknown usage explicitly.
- [ ] Isolate provider work and test the broker from real restricted containers,
  including routing overrides, cross-run access, malformed input, failure and
  cleanup. Remote requests may continue after local cancellation.
- [ ] Implement a fresh restricted scorer without broker, host network, private
  storage, or hidden checks. Trusted evaluator code remains outside and judges
  bounded input/output/exit status; agent-generated code never runs on the host.
- [ ] Independently test malicious artifacts, scoring integrity, hidden-check
  isolation, limits, failure classification and cleanup. Review the complete
  execution-to-scoring path before real benchmark use.

**Exit:** a reviewed end-to-end boundary using fixed test programs and fake
providers, with task failures distinct from infrastructure failures.

## Milestone 4 — first report-only benchmarks

The case format, suite loader, report formatting, and deterministic orchestration
can be developed against fake executors in parallel with milestones 1–3. Such
fakes must never be labelled as sandboxed or used to run real agent work.

- [ ] Complete required case/run provenance, safe config fingerprints,
  private storage, and status contracts. Reject unknown suites and unsafe paths.
- [ ] Create a few versioned, sanitized coding fixtures with independent
  black-box checks, and review fixtures with known defects and structured output.
- [ ] Implement a report-only runner with explicit suite/agent selection,
  per-case results, timestamps, actual available usage/cost, and infrastructure
  error reporting. Review-case defect matching remains pending human review.
- [ ] After milestones 0–3 are accepted, run the first disposable suite, record
  results in explicit private storage, and repeat runs to expose variation.
  No quality outcome becomes a CI gate.

**Exit:** a person can run and inspect a small benchmark against two agent
configurations, with separate pass/fail/pending/infrastructure counts and no
claim that a single run proves readiness.

## Later: trace-driven improvement

- [ ] Validate and import traces with provenance; enforce a locally controlled
  model and no external network or MCP for trace review. The local-only broker
  enforcement mechanism remains an unresolved security gate.
- [ ] Generate evidence-linked case and prompt/skill/harness proposals; record
  human accept/reject/revision decisions and require separate explicit promotion.
- [ ] Compare reviewed candidates against existing suite versions with repeated
  runs. Never automatically apply proposals or upload private traces.

## Delivery and review rules

- [ ] Use red/green tests for each behavior; report unavailable runtime tests
  explicitly. Keep potentially expensive or risky integration tests opt-in.
- [ ] Maintain `agent-evaluation-implementation.md` and user-facing docs; do not
  mark a design proposal, mock, or partial observation as completed enforcement.
- [ ] Request user decisions before changing isolation, runtime, network,
  resource-policy, or destructive recovery choices. No tool-call approvals are
  introduced into agent runs.
