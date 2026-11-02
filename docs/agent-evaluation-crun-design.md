# Standalone rootless crun controller: proposed design

**Status: draft for security and implementation review. Not implemented, not
approved as a sandbox, and not permission to run untrusted benchmarks.** This
proposes an alternative to the initial Podman-managed benchmark profile in
`docs/agent-evaluation-sandbox.rst`. The existing Podman diagnostics remain
useful evidence about that separate profile; they do not verify this one.

## Motivation and scope

Rootless Podman 5.8.9 on the development host rejects the tested tmpfs inode
options. A one-off, rootless direct-OCI `crun` diagnostic passed
`nr_inodes=128` to a private tmpfs and hit `ENOSPC` after 114 file creations.
The diagnostic used a temporary OCI root filesystem and network/user/mount
namespaces. It did **not** establish the production controls below: its
cgroup manager was disabled, and seccomp, LSM, network isolation, lifecycle,
and recovery were not independently verified. The result is feasibility
research, not an approved mechanism or security proof.

The proposed first production profile is a **standalone rootless `crun`
controller on Linux**, not a Podman-managed lifecycle. The controller is a
trusted host process. It prepares a fresh OCI bundle and owns a dedicated
runtime-state root, cgroup, per-run model broker, teardown, and recovery.
`crun`, the kernel, the broker, the image and its trusted startup verifier,
the controller, and the evaluator are part of the trusted computing base.
Containers share the host kernel and are not VM-equivalent. A malicious host
user with the same identity, privileged users, kernel/runtime compromise,
provider compromise, and malicious trusted images are outside this boundary.
Choose a stronger isolation boundary when those risks are unacceptable.

Only fixed, disposable diagnostics may be run while implementing this design.
No benchmark agent, arbitrary fixture code, or scorer workload may run until
all rollout gates have been independently verified and reviewed. No silent
fallback to local execution, ordinary Docker, or a weaker profile is allowed.

## Controller-owned inputs and runtime

- A trusted operator configures supported `crun` versions, OCI/runtime-spec
  version, rootless Linux/cgroup prerequisites, trusted images, policy files,
  per-case limits, and explicitly permitted model routing. Reject unsupported
  or unknown values. Agent/model output cannot select runtime flags, OCI
  mounts, host paths, images, credentials, policy, cgroup locations, or limits.
- Provision a reviewed image by pinned digest and verify its provenance through
  an independently specified trusted process. A digest identifies content; it
  is not proof of provenance. The image provisioning and root filesystem
  assembly are trusted operations and must not execute image-controlled hooks
  or processes. An optional trusted image provisioner is separate from the
  standalone `crun` lifecycle; the design does not depend on a runtime socket.
- Create a fresh private OCI bundle and rootless runtime-state directory for
  each run. The container root is an immutable, read-only prepared image root
  filesystem—not the user's checkout. Do not mount the live workspace, host
  home, credentials, runtime sockets, scoring checks, private traces, or host
  environment. The OCI root filesystem itself is runtime-managed host storage;
  “no host mounts” means no arbitrary host bind mounts are exposed to the
  workload, apart from the narrowly scoped broker socket described below.
- Verify the rootless `crun` binary and required kernel/runtime features at
  startup and during preparation. Pin or otherwise verify the runtime and OCI
  policy versions. Record non-secret identities and hashes. The existing
  Podman preflight must not authorize a standalone `crun` run.

## Isolation and resource policy

The controller generates OCI configuration from a fixed, reviewed policy; it
does not accept arbitrary configuration or hooks from agents or fixtures.
A trusted verifier checks both the generated policy and the **effective running
state** before any untrusted content executes. Missing support or inconclusive
verification is an infrastructure error, never a warning followed by execution.

- Create fresh user, mount, PID, IPC, UTS, and network namespaces. Map only the
  minimum required UIDs/GIDs; run the agent as a non-root container UID and
  GID, with an empty capability set and `noNewPrivileges`. Root inside a user
  namespace is still a privileged identity *within that namespace*; do not
  confuse lack of host root with a non-root workload. Verify mappings,
  effective credentials, namespace membership, and capabilities.
- Use a reviewed seccomp allowlist and an applicable enforced LSM profile;
  verify the effective policy. Specify host prerequisites and behavior when an
  LSM is unavailable. Do not accept a runtime's success exit alone as proof.
- No external network, including DNS and host services. Independently probe
  IPv4, IPv6, DNS and selected host endpoints. The single per-run broker Unix
  socket is the only intended communications exception. Expose only that socket,
  not its host parent directory, and validate permissions and run identity.
- Mount a bounded tmpfs workspace with explicit byte **and inode** limits,
  `nosuid`, `nodev`, and other reviewed flags. Apply explicit bounds and inode
  limits to **every** writable filesystem, including `/tmp`, `/dev/shm`, and
  any runtime-created writable mounts; a workspace quota alone is insufficient.
  Do not grant untrusted processes permission to remount or create mounts.
  Verify inode totals and actual `ENOSPC` behavior, as well as byte limits.
- Allocate a dedicated delegated cgroup v2 subtree for each run through a
  reviewed, rootless mechanism, such as a verified systemd user delegation.
  Apply and independently read back memory, swap, CPU, and PID limits before
  release. Test that untrusted descendants cannot move themselves or alter
  limits. If delegation or enforcement is unavailable, fail closed. Do not use
  `--cgroup-manager=disabled` for workloads; it was used only in the inode
  feasibility test.
- Enforce wall time outside the container, bounded logs and broker traffic,
  file count, artifact size, and resource cleanup. Concrete limit defaults are
  an explicit operator/security decision, not yet approved by this document.
  A model request may continue remotely after local cancellation.

## Lifecycle and pre-execution verification

1. Validate the case, approved image/policy, rootless runtime and cgroup
   prerequisites. Create a unique run ID and private controller-owned state;
   write a durable lifecycle record **before** creating external resources.
   Never include credentials, arbitrary prompts, or raw traces in this record.
2. Prepare the image root, sanitized fixture inputs, OCI bundle, resource
   cgroup and broker without exposing authoritative checks or private storage.
   Verify content hashes and the expected image provenance. Reject unsafe paths
   and metadata during provisioning.
3. Create the container with a **trusted startup verifier**, not the untrusted
   agent as the initial command. Do not load fixture-controlled libraries,
   hooks, shell configuration, or executable content during verification. The
   verifier waits on a dedicated, single-use controller release channel.
4. Independently inspect runtime state, namespace/mount/cgroup policy and the
   startup verifier's effective environment. Confirm the init identity and the
   effective security controls against the trusted policy. The exact race-free
   verification and release protocol is a **blocking design item**: describe
   how the controller authenticates the verifier, prevents a substituted process
   or forged report, and binds the checks to the same container and cgroup.
   A test within the container by itself is not sufficient proof. No release
   means no untrusted execution.
5. Release the verifier only after every required check passes; it starts the
   agent and remains responsible for reaping its descendants. The agent and
   all its tool subprocesses remain inside the same verified boundary. The
   broker binds the provider/model on the host and applies its own limits.
6. Enforce the deadline and record a non-secret outcome. On any setup, model,
   verifier, or cleanup failure, preserve diagnostic state and distinguish an
   infrastructure error from a task failure. `ready` remains false until this
   lifecycle and all acceptance gates are implemented and reviewed.

The release channel and broker socket have different purposes. The release
channel is controller-to-trusted-verifier, one-shot, and must not be retained
by the agent. The broker is intentionally available to the agent with
run-scoped, narrowly limited authority. A broker request can carry fixture
content to an approved remote provider: network isolation does not prevent
exfiltration through that channel, so only sanitized data may be used.

## Quiescence and artifact export

A tmpfs workspace normally disappears when its mount namespace is destroyed.
Therefore “stop the agent, then export” must not mean deleting the container
before collecting artifacts. The proposed sequence is:

1. Finish the agent run or, on timeout, prevent further agent work. Freeze the
   **entire run cgroup**, verify the kernel reports all its processes frozen,
   and keep a verified namespace-holding process alive. If freezing, process
   identity, namespace retention, or observation cannot be verified, do not
   export; report an infrastructure error. The precise lifecycle for a run
   whose init has already exited is unresolved and must be designed and tested.
2. While the whole untrusted cgroup remains frozen, a trusted collector outside
   the container reads only explicitly allowed relative paths via held directory
   descriptors. It uses race-resistant no-follow/beneath resolution and rejects
   symlinks, hard links, special files, mount crossings, duplicate/colliding
   names, oversized data, and excessive depth or file count. Never untar an
   untrusted archive or execute collected files on the host. If kernel or
   permission semantics prevent safe collection, fail closed. Confirm that no
   process outside the frozen cgroup can mutate the workspace.
3. Copy validated artifacts into a private staging area with restrictive
   permissions and immutable hashes. Then kill and delete the container,
   broker, cgroup, and bundle, and independently verify removal. A separate
   restricted scorer receives only the intended artifact. The trusted evaluator
   stays outside the scorer and keeps hidden checks and expected answers out
   of the agent/scorer environment; use the black-box scoring rules in
   `agent-evaluation-sandbox.rst`.

This is a proposal, not a claim that `/proc` access, cgroup freezing, user
namespace permissions, or safe collection are available on this host. Verify
those mechanics with trusted disposable probes before implementing a runner.
Do not weaken them to make export succeed.

## Crash recovery and ownership

- A durable, owner-only run ledger records the unique run ID, expected runtime
  state-root identity, resource identifiers, creation stage, and versioned
  ownership evidence before each external creation. Use atomic updates and
  directory synchronization where supported. Store no authentication tokens.
  Recovery must work if a crash occurs between any resource operation and its
  ledger update; define how each creation is reconciled without trusting names
  alone.
- Use an exclusive controller/recovery lock plus process identity stronger
  than PID alone (for example boot ID and process start time). Never recover a
  run that may still be active. PID reuse, reboot, partial writes, inaccessible
  state, stale locks, concurrent recoverers, and ambiguous identity must fail
  closed. A lock alone is not a substitute for verified ownership.
- Reconcile only resources independently proven to belong to the specific
  recorded run under the dedicated runtime/cgroup roots. Do not scan or kill
  arbitrary host processes or containers, trust an agent-provided path, or use
  broad `--all` cleanup. Define exact ownership checks for cgroups, bundle,
  broker socket, and OCI state before implementing automatic recovery.
- Kill the verified run's complete cgroup, stop broker access, delete OCI state,
  and remove only verified owned resources. Verify each removal; preserve a
  recoverable infrastructure-error record when any step is uncertain. Cleanup
  must be bounded and safely repeatable. A process kill or successful command
  exit is not by itself proof that resources are gone.

The existing exact-ID Podman crash diagnostic does not implement this ledger
or establish any of these standalone `crun` recovery guarantees.

## Design review and rollout gates

- [ ] Security-review the trust boundary, host threat model, and shared-kernel
  risk; decide whether rootless containers are sufficient or a VM is required.
- [ ] Specify approved runtime and image provenance, rootless UID/GID mapping,
  seccomp and LSM policies, cgroup delegation, and concrete resource limits.
- [ ] Specify and review race-free verifier/release, per-run broker transport,
  socket authorization, and the local-only trace-review routing boundary.
- [ ] Prove all writable mounts have byte and inode limits and cannot be
  replaced; test workloads that exhaust each limit in disposable environments.
- [ ] Prove runtime restrictions with independent host-side inspection and
  adversarial in-container probes, including both successful and weakened
  controls. Do not infer enforcement solely from OCI config or runtime reports.
- [ ] Resolve and test freeze/namespace-holding export, race-resistant artifact
  collection, scorer isolation, and black-box evaluator limits.
- [ ] Specify and test durable creation, controller-crash/reboot recovery,
  ownership, process reuse, concurrent recovery, timeout, and orphan cleanup.
- [ ] Complete provider broker limits, trace privacy, fixture curation, status
  reporting, and a documented test matrix with explicit unsupported outcomes.
- [ ] Obtain independent security review of the design **and implementation**;
  keep all real benchmark execution unavailable until the gates are accepted.

No item above is marked complete by the inode feasibility experiment. Existing
contracts, fake-provider broker, and Podman probes do not implement this
controller. Tests for future implementation must include a red/green unit-test
layer and real, disposable rootless `crun` integration tests.
