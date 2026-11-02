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
