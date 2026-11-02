Evaluation sandbox and trusted scoring: proposed design
=======================================================

**Status: proposed for security review; not implemented or verified.** This
specification does not make the existing Docker environment a benchmark
sandbox. Do not run untrusted benchmark agents or patches under this design
until its enforcement and integration tests exist and the security boundary
has been reviewed. A read-only preflight reports runtime capabilities but
always rejects readiness; see :doc:`agent-evaluation`. It extends ``docs/agent-evaluation-plan.md``; where that
plan is broader, this document describes the earlier Podman-oriented profile.
A standalone rootless ``crun`` alternative is proposed in
``docs/agent-evaluation-crun-design.md``; neither profile is approved or ready.

Purpose and threat model
------------------------

Run a coding or review agent on a disposable fixture and score its work without
exposing the host workspace, credentials, private traces, or authoritative
checks to agent-controlled code. Treat model output, tool arguments, fixture
content, agent-generated files, and program output as hostile. A malicious
agent may try to escape its workspace, access the network, consume resources,
forge results, tamper with checks, or send sensitive data through the model.

This profile targets **rootless Podman on Linux**. Podman, its configuration,
the Linux kernel, the host operator, the broker, trusted evaluator, and reviewed
images are trusted. Containers share the host kernel and are not a security
boundary against kernel or runtime exploits, a hostile host user, or a
compromised model provider. Use a disposable VM or stronger boundary if that
risk is unacceptable. macOS, Windows, rootful Podman and Docker are unsupported
for this profile until separately specified and tested.

Model access and confidentiality
--------------------------------

A host-controlled broker is the only model interface available to the agent
container. The container has no general network. The agent connects through a
narrow, per-run Unix socket exposed to the container; no host directory, Docker
socket, Podman socket, or credential file is mounted. The broker is a separate
service and must not execute instructions or commands from the agent.

* The controller selects the model, provider, endpoint and authentication
  outside the container. The broker rejects requests to choose or override any
  of them and never returns credentials or sensitive headers.
* The broker accepts only a bounded, validated model-request protocol, with
  run-scoped authentication, concurrency, request-size, response-size, token,
  cost and wall-time limits. It is not a generic HTTP proxy or filesystem API.
  Its endpoint is reachable only by the intended run, and it closes when the
  run ends. Model response text and tool calls remain untrusted.
* Coding and review benchmarks may use an explicitly configured remote model.
  Everything the agent submits to that model, including fixture contents and
  tool results, may leave the host. Only use sanitized fixtures with approved
  providers. Disabling container networking does not prevent exfiltration via
  the broker. The broker cannot reliably distinguish secrets in free text.
* Trace review is a separate, stricter profile: raw traces must reach only a
  locally controlled model. Broker routing must enforce the local model at the
  transport boundary, with no external egress and no MCP access. A loopback
  URL, configuration string, or prompt instruction alone does not prove this.
  The precise enforcement mechanism is a **blocking design decision**; do not
  implement or enable trace review until it is specified and independently
  tested. Local traces and proposals still require private storage.

Agent container contract
------------------------

The controller creates one fresh, disposable rootless container per case and
run from an approved image pinned by digest. Image provenance and updates are
reviewed separately; a digest proves identity, not trust. No live repository,
host home directory, credentials, runtime socket, scoring checks, run storage,
or host environment is mounted or forwarded. Provision only an explicit,
sanitized fixture and the per-run broker socket.

The adapter must verify the effective runtime configuration before starting the
agent and fail closed if it cannot establish any required control:

* A rootless runtime and non-root container user; no privileged mode, host PID,
  IPC, network, user namespace sharing, host devices, or elevated capabilities.
  Drop all capabilities, set no-new-privileges, and enforce a reviewed seccomp
  policy and applicable LSM policy. Do not accept agent-controlled run flags.
* Network namespace with no external network; deny outbound DNS, IPv4 and
  IPv6. Verify this independently, including host services. The broker Unix
  socket is the only permitted communications exception.
* Read-only container root; only bounded disposable writable workspace and
  temporary filesystems. Enforce per-run disk/inode quotas with a mechanism
  proven on the chosen runtime and filesystem. Never assume a tmpfs size limits
  the host memory used by all runtime components.
* Enforce CPU, memory, process count, output, file count, artifact size and
  wall-time limits. Limits are operator-owned, recorded with the run, and not
  controlled by the agent. Select concrete defaults and validate support before
  implementation; a host request timeout alone is not a run deadline.
* Run no untrusted content before the effective policy is verified. On timeout,
  cancellation or failure, terminate the container and verify it is gone; if
  termination or verification fails, report infrastructure error and retain
  enough non-secret identifiers for cleanup. Do not present an unverified
  teardown as success. Recover orphaned resources after controller crashes.

The agent and its tool execution are inside this boundary; the broker and
trusted evaluator are outside. Merely putting shell commands in a container
while leaving the agent process with host access does not satisfy this contract.
Network isolation and the runtime socket checks must apply to every process,
including helpers and tool subprocesses.

Artifact transfer and scoring
-----------------------------

1. Stop agent execution before export. Export only explicitly permitted file
   paths or a patch from the disposable fixture, with limits on bytes, files and
   processing time. Treat the export as hostile: reject absolute paths, ``..``,
   symlinks, hard links, special files, duplicate entries, path collisions and
   unexpected metadata. Use race-resistant traversal and staging; never extract
   untrusted archives directly onto the host. Do not follow links or write into
   the live checkout. Reject unsupported artifacts rather than guessing.
2. A trusted controller checks fixture and case identities, records immutable
   hashes, and places the validated artifact in a fresh scorer environment.
   The scorer environment has restrictions at least as strong as the agent
   environment, no model broker, no network, no private storage or hidden
   checks, and no host credentials. Do not execute agent code on the host.
3. A trusted evaluator outside the scorer owns the authoritative checks and
   expected findings. The first coding cases must use a **black-box protocol**:
   the evaluator sends bounded test inputs to the untrusted program and checks
   bounded outputs and exit status outside the scorer. Hidden test code and
   expected answers are never mounted or sent into the scorer. The program
   necessarily sees the inputs it is asked to process and may infer information
   from them; do not claim complete secrecy of test inputs. Do not expose a
   general host command, filesystem, network, or evaluator API to the program.
4. Cases that cannot be scored through this protocol are unsupported until a
   separately reviewed design exists. Never mount a normal hidden test suite
   into the same environment as agent code and call it isolated. On malformed
   artifacts, unsupported cases, verification failure, or evaluator failure,
   record an infrastructure error rather than a pass. Test assertion failures
   are task failures; define ambiguous error cases explicitly in each case.
5. Review benchmarks validate output structure and workspace invariance, then
   remain pending human review for matching expected defects and false positives.
   Human review is not a tool-call approval and does not block agent execution.

Checks and rollout gates
------------------------

Before enabling any real execution, specify the broker protocol and exact
runtime/image requirements, limits, fixture and export formats, black-box case
protocol, local-only trace-review networking, and recovery procedure. Obtain
security review of those choices and of the actual implementation. Tests must
exercise a disposable test fixture, not the user's live workspace or secrets.

Acceptance requires integration tests against the actual supported rootless
runtime, not just mocks:

* Inspect and probe effective UID, capabilities, seccomp/LSM, mounts, runtime
  socket absence, read-only root, filesystem quotas, process and memory limits.
  Verify unsupported or weakened settings fail closed.
* Probe DNS, IPv4/IPv6 and host-service access; confirm the broker accepts only
  the selected model protocol, rejects routing overrides, prevents cross-run
  access, and enforces its limits. Test broker shutdown and partial requests.
* Exercise path traversal, absolute paths, links, special files, oversized
  output and artifacts, and races during extraction. Verify the host workspace,
  hidden checks and private storage are neither readable nor writable from
  agent and scorer containers.
* Use deliberately adversarial programs to attempt to read or alter checks,
  forge outcomes, reach host services, consume resources, or outlive a timeout.
  Verify evaluator-owned verdicts and distinguish test failure from
  infrastructure failure. Test interrupted runs, controller crashes, failed
  cleanup, and orphan recovery.
* Verify trace-review local-only routing separately, including blocked external
  egress and MCP; until then trace review remains unavailable.

All results are report-only. The implementation must not silently fall back to
local execution or ordinary Docker, or enable automatic proposal promotion.
