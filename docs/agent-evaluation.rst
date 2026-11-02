Agent evaluation foundations
============================

The benchmark and evaluation packages contain versioned data contracts and
private JSON storage and read-only runtime diagnostics. They do **not** run
benchmarks, judge reviews, import
trajectories, isolate agents, or provide a CLI. The next phases are described
in ``docs/agent-evaluation-plan.md``. The proposed threat model and isolation
contract are in :doc:`agent-evaluation-sandbox`. A standalone rootless crun
alternative is proposed in ``docs/agent-evaluation-crun-design.md``.

Contracts
---------

The Python APIs are ``workshop.agent_benchmark.contracts`` and
``workshop.agent_eval.contracts``. Their Pydantic models reject unknown fields;
all have ``schema_version: 1``. Use ``model_validate_json()`` to validate JSON,
``model_dump(mode="json")`` for serializable data, and
``model_json_schema()`` for the full machine-readable schema. These first
schemas are experimental and may change before a runner is introduced.

* ``Case`` contains an ID, positive version, coding/review role, task, fixture
  ID and SHA-256, scoring method and version, and optional constraints.
* ``CaseRef`` identifies a case by ID and version. ``Suite`` contains an ID,
  version, role, and nonempty list of unique case references. Fixture and
  scoring contents are not stored in these definitions.
* ``TraceReference`` contains an ID, format, SHA-256, storage key, source, and
  redaction flag. It is metadata only; it does not validate a trajectory or
  verify its hash or redaction.
* ``CaseResult`` identifies a case and one of ``pass``, ``fail``,
  ``pending_human_review``, or ``infrastructure_error``. ``RunResult`` records
  the suite identity and hash, agent ID, case results, optional trace reference,
  and optional usage and cost. Missing measurements remain null.
  ``aggregate_outcomes`` returns separate counts, including zero counts; it
  does not infer a pass or quality gate.

These models validate structure, not the correctness of tasks, hashes,
redaction claims, or results. Prompt/config fingerprints, timestamps, human
judgments and proposal contracts are not implemented yet.

Sandbox preflight diagnostics
-----------------------------

``workshop.agent_benchmark.preflight.preflight()`` checks whether the host is
Linux and whether local Podman reports rootless operation, seccomp, cgroups v2,
and the CPU, memory, and PID controllers. It runs only ``podman info`` with a
timeout; it does not start a container, contact a model, or run an agent.
Missing or malformed information is not treated as a pass. Reports retain
separate ``pass``, ``fail``, and ``unverified`` states.

These are self-reported runtime capabilities, **not proof of enforcement**.
The effective sandbox, broker, artifact handling, scoring, cleanup, and
security review remain unverified. ``ready`` is deliberately always false;
there is no execution path, override, or fallback. For example:

.. code-block:: python

   from workshop.agent_benchmark.preflight import preflight

   report = preflight()
   print(report.checks)
   assert not report.ready

Experimental broker prototype
-----------------------------

``workshop.agent_benchmark.broker.ModelBroker`` is an in-process, text-only
prototype tested with injected asynchronous fake providers. It is not connected
to any model provider or benchmark runner and is **not security-reviewed**.
It does not enforce token, cost, network, or trace-review restrictions. Do not
use it to isolate untrusted agents or real credentials.

It creates a single-use Unix socket in an existing owner-only directory, with a
per-instance secret. Requests are newline-delimited UTF-8 JSON objects with
exactly ``version`` (integer 1), ``token``, and a nonempty ``messages`` array;
each message has only ``role`` (``system``, ``user`` or ``assistant``) and
string ``content``. Model and endpoint overrides and duplicate JSON fields are
rejected. Responses contain ``ok`` and either ``content`` or a generic ``error``.
The wire protocol is experimental and does not yet support native tool calls.

The prototype limits request frames to 256 KiB including the newline, response
frames to 1 MiB including the newline, concurrent provider calls to one, and
valid authenticated calls to 20 per instance. The frame-read and provider-call
budget is 30 seconds; writes have a separate timeout. The limits may be lowered
for tests. Provider code is trusted and runs in the same event loop; a blocking
or cancellation-resistant provider cannot be forcibly stopped by this
prototype. Timeout and cleanup do not prove remote work has stopped.

Disposable runtime diagnostic
-----------------------------

``workshop.agent_benchmark.probe.run_probe()`` runs a fixed diagnostic in a
fresh rootless Podman container using a pinned, locally available Fedora image.
It never pulls the image, mounts the workspace, contacts a model, or runs agent
code. It requires the preflight runtime capability checks to pass. The
container uses the initial probe limits: one CPU, 512 MiB memory, 128 processes,
a 64 MiB temporary filesystem, and a 30-second execution timeout. The probe
attempts removal and checks container absence afterward.

Its output reports the container's observed UID, capabilities, seccomp mode,
no-new-privileges, root mount mode, network interfaces and cgroup/tmpfs values.
A passing observation is not proof of isolation: in particular, checking for
only a loopback interface is not a network reachability test. The image and
runtime are trusted; image digest pinning is not provenance verification.
Missing observations remain unverified, cleanup can be unverified, and
``ready`` always remains false. No agent workload is enabled by this probe.

``workshop.agent_benchmark.boundary_probe.run_boundary_probe()`` adds a second
fixed diagnostic. It tests routes to one IPv4 and one IPv6 documentation
address, a temporary host loopback listener, a write to the container root,
common Docker/Podman socket paths, a bounded tmpfs fill, and the cgroup PID
limit. It inspects Podman's reported network mode and mounts, then attempts
container removal. The DNS check reports unverified when resolution fails,
because that failure does not prove network isolation. Route and loopback
results apply only to the specific tested endpoints; root write failure as a
non-root user does not prove the filesystem is read-only. Socket checks cover
only the named paths, and reported mounts do not prove no host data is
accessible by another route. All observations trust the diagnostic image and
runtime. ``run_timeout_probe()`` separately times out a fixed sleeping
container, attempts a kill and removal, and checks whether the container is
gone. A timeout before container creation is inconclusive. These checks are not
a security certification, an exhaustive penetration test, or an agent-execution
gate. If cleanup cannot be verified, check for and remove leftover
``workshop-boundary-*`` or ``workshop-timeout-*`` containers. Automatic crash
recovery is not yet tested. A separate 64 MiB memory-pressure diagnostic is
described below.

``workshop.agent_benchmark.dns_probe.run_dns_probe()`` uses a temporary DNS
listener on host IPv4 loopback and verifies the exact diagnostic query and
known answer locally before starting a network-disabled container. It reports
whether that container's query reaches the listener or receives an answer;
missing, malformed or ambiguous observations are unverified. This tests only
that particular host loopback UDP endpoint, not the system resolver, IPv6 DNS,
other host addresses, or general DNS isolation. The listener closes afterward;
if cleanup cannot be verified, check for leftover ``workshop-dns-*``
containers. Benchmark readiness remains false.

``workshop.agent_benchmark.resource_probe`` provides fixed memory and inode
diagnostics. The memory probe applies pressure inside a container capped at
64 MiB with swap disabled and requires both the observed cgroup limit and
Podman's OOM indication before reporting a pass. The inode probe requests a
128-inode tmpfs and requires a verified inode count and a no-space error.
Runtime errors and ambiguous observations do not establish enforcement. On the
local Podman 5.8.9 setup, ``nr_inodes=128`` is rejected as an unknown tmpfs
mount option, so the inode probe cannot run and remains unverified. Tests of
``--mount type=tmpfs`` with ``tmpfs-inodes``, ``nr_inodes``, and ``inodes``
were also rejected. Podman's local documentation describes inode quotas for
XFS project-quota-backed volumes, not tmpfs volumes, and notes that local
volume options other than UID/GID require root privileges. This host stores
rootless container data on Btrfs. No suitable mechanism has been established
under the current no-host-mount and no-elevation constraints. A supported
quota mechanism and independent verification are still required. A tmpfs byte
or cgroup memory limit is not an inode quota. A separate manual rootless OCI
``crun`` diagnostic bypassed Podman's CLI parser: an OCI tmpfs with
``nr_inodes=128`` reported 128 inodes and returned ``ENOSPC`` after 114 files.
The throwaway bundle and runtime state were removed. This demonstrates a
possible low-level route, not a verified benchmark sandbox: the experiment did
not establish the complete cgroup, seccomp, LSM, networking, lifecycle, or
recovery controls. Direct OCI runtime integration needs a separate design and
security review. These probes consume bounded host resources and run only with
operator approval.

A separate opt-in integration test exercises a controller crash and recovery of
one explicitly identified diagnostic container. ``recover_probe`` requires its
full ID, exact diagnostic name, matching random label, and a locally reported
rootless Podman runtime; it checks identity before sending kill or remove and
verifies absence afterward. It does not scan for or automatically remove
orphans, persist recovery records, handle host crashes, or provide production
benchmark recovery. Run the disposable test only with permission:

.. code-block:: shell

   WORKSHOP_PODMAN_CRASH_TEST=1 pipenv run pytest \\
     tests/test_benchmark_recovery_integration.py

The test uses a pinned local image and does not pull it. A failure can leave a
``workshop-crash-*`` container; inspect and remove only the identified test
container if needed.

Standalone controller cgroup diagnostic
---------------------------------------

``workshop.agent_benchmark.crun_cgroup_probe.run_cgroup_probe()`` creates a
unique transient user-systemd service running only a fixed sleep command. It
checks the service's reported delegation setting, reads back 64 MiB memory,
32-process and 50% CPU limits, and observes the cgroup's frozen and thawed
states. It then stops that service and checks both unit and cgroup removal.
It does not invoke ``crun``, run an agent, or enable benchmark execution.
Run it only with permission: it creates and controls a real user service.

A reported ``Delegate=yes`` is not proof that a controller can create and
manage a delegated child cgroup, that descendants cannot change limits, or that
the proposed OCI controller works. The freezer observation is not proof of
safe artifact export. A failed or timed-out start can leave cleanup unverified;
the report includes the exact unit name for investigation. Readiness remains
false. The proposed standalone controller and its outstanding review gates are
in ``docs/agent-evaluation-crun-design.md``.

``workshop.agent_benchmark.crun_child_cgroup_probe.run_child_probe()`` is a
separate diagnostic that starts a fixed transient user service. The service
moves itself into its own delegated child cgroup, enables the CPU, memory,
and PID controllers, and sets bounded child limits including zero swap. It
starts a fixed sleep descendant. The host diagnostic checks both processes'
identity and membership, observes populated freeze/thaw states and membership
at each checkpoint, then stops the service and checks cgroup removal. Run it
only with permission; it changes a real user-service cgroup. Results and an
exact unit name are reported even when cleanup is unverified. This is not a
``crun`` container, does not prove untrusted descendants cannot escape or
change limits, and does not implement artifact export or benchmark execution.

Frozen tmpfs export feasibility
-------------------------------

The opt-in ``tests/test_crun_export_integration.py`` diagnostic starts a fixed
synthetic program in a throwaway rootless ``crun`` OCI bundle inside a
delegated user-service child cgroup. It observes that the init process belongs
to that child, freezes the populated cgroup, and reads one known synthetic
file through a host-opened ``/proc/<pid>/root/tmp`` directory descriptor. It
then verifies the group is still frozen and the init has not exited, thaws and
kills the service, and checks runtime and cgroup cleanup.

This test requires Linux, user systemd, ``crun``, ``gcc``, the x86-64 dynamic
loader and libc at ``/lib64``, and ``pidfd_open``. It is opt-in because it
creates namespaces and changes a disposable user-service cgroup:

.. code-block:: shell

   WORKSHOP_CRUN_EXPORT_PROBE=1 pipenv run pytest \\
     tests/test_crun_export_integration.py

The fixed-file reader is a diagnostic only: it is not a general safe artifact
collector and does not prove safe path traversal, mount-boundary handling,
race resistance against hostile processes, or that no external process can
mutate the workspace. The diagnostic runs a fixed trusted program as UID 0
inside its user namespace, without the final seccomp/LSM policy or runtime-managed
cgroup setup. It does not establish a secure benchmark sandbox. A first cleanup
attempt timed out because a container init remained alive; the diagnostic now
tries KILL before stopping and verifies cleanup. Failures may still leave a
``workshop-export-*`` user service or OCI runtime state that needs investigation.
Benchmark readiness remains false.

Inherited release-pipe experiment
---------------------------------

``workshop.agent_benchmark.crun_release_probe.run_release_probe()`` starts a
fixed local test process with a one-way inherited pipe. It tests default denial,
a simulated successful check, simulated PID mismatch, forged child messages
(including a spoofed success marker), a closed channel, and descriptor cleanup.
The fixed test child does not start an agent; its output is never sufficient to
authorize a release.

The check flag and identity mismatch are **simulated**. A separate opt-in
``tests/test_crun_release_integration.py`` test passes a pipe through a real
rootless ``crun`` bundle to a fixed verifier program. It exercises denial,
simulated approval and PID mismatch, an invalid byte, forged child output, and
closing FD 3 before executing a fixed follow-up program. The test checks the
runtime state and, when available, the verifier pidfd at cleanup:

.. code-block:: shell

   WORKSHOP_CRUN_RELEASE_PROBE=1 pipenv run pytest \\
     tests/test_crun_release_integration.py

This is not a production release protocol: the test runs UID 0 inside a user
namespace with the ``crun`` cgroup manager disabled and without the final
seccomp/LSM policy. It does not authenticate a container verifier or verify
namespaces, cgroups, effective policy, or race resistance. The mismatch is
simulated, not a real process-substitution attack, and child output is not
security evidence. Readiness remains false, and the real handshake still needs
independent security review.

Private storage
---------------

``PrivateStorage`` in ``workshop.agent_eval.storage`` requires an explicit
root path; there is no default or implicit repository storage. Its parent must
already exist. On POSIX it creates the root with owner-only permissions, checks
ownership and permissions on access, and uses owner-only files, single-component
``.json`` keys, no-follow opens, and atomic replacement. It rejects an insecure
existing root and does not support non-POSIX systems. Example:

.. code-block:: python

   from workshop.agent_eval.storage import PrivateStorage

   store = PrivateStorage("/private/runs")  # /private must already exist
   store.write_json("example.json", {"status": "pending_human_review"})
   record = store.read_json("example.json")

Choose a trusted directory outside the agent workspace. Existing ancestor
directories and the host must be trusted: this is not a sandbox or a defense
against the owner or privileged processes. Storage accepts arbitrary JSON and
does not detect, redact, or encrypt secrets; callers must decide what they
persist and protect backups. The file and directory checks do not validate or
sanitize trace contents. Interrupted writes can leave temporary files; remove
those only after checking no writer is active.
