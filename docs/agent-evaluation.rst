Agent evaluation foundations
============================

The benchmark and evaluation packages provide report-only local benchmarks,
private JSON records, comparisons, optional trace capture, human decisions,
and an experimental trace-review prototype. They do not automatically judge
review findings, import arbitrary external trajectories, or isolate agents.
The proposed isolation boundary in :doc:`agent-evaluation-sandbox` remains
unimplemented and unreviewed. See ``docs/agent-evaluation-plan.md`` for the
broader proposal.

Local benchmark
---------------

**Only use trusted agents, configurations, and fixtures.** Agent tools and
coding checks execute with your user permissions. The temporary working
directory is not a sandbox; agents may access other files, credentials, the
network, and configured MCP servers. A remote model may receive fixture data.
Private records can contain sensitive output and are not automatically redacted.

Select a named agent and one of the bundled suites: ``coding-v1`` and
``review-v1`` have one starter case each, the v2 suites have three cases, and
the v3 suites have six cases covering different failure modes, including
multi-file coding fixtures. The ``pr-review-v5`` suite reviews synthetic pull
requests. Earlier suite identities and hashes are preserved.
The explicit storage directory must be owner-only and its parent must already
exist. For example:

.. code-block:: bash

   workshop benchmark run --suite review-v1 \\
     --agent reviewer --storage "$HOME/private-benchmarks" --local
   workshop benchmark report RUN_ID --storage "$HOME/private-benchmarks"

PR-review cases
~~~~~~~~~~~~~~~

The ``pr-review-v5`` suite evaluates the :doc:`PR review agent <pr-review>`
against synthetic pull requests. Each case pins a fixture of canned GitHub API
responses by SHA-256. During the run, the benchmark starts a disposable HTTP
server bound to ``127.0.0.1``, points the GitHub tools at it through the
``WORKSHOP_GITHUB_API_BASE`` environment variable, and restores the variable
afterwards. The service accepts loopback overrides only and does not send
``GITHUB_TOKEN`` or use environment proxies for fixture requests. This does not
restrict other tools, plugins, or the model provider. One case
contains a planted defect; another is a benign rename with no findings. Both
produce ``pending_human_review`` outcomes with the agent's findings and the
expected findings in the report details, and require a human judgment like any
review case. The loopback server is trusted-local test infrastructure; it is
not a network boundary. A remote model may receive synthetic fixture content,
and other configured tools may access the network. ``pr-review-v4`` and its
underlying ``pr-review-v1`` fixture contain invalid Python source; they are
retained for historical report identification but cannot be run. Do not use
past results from these suites to judge reviewer quality.

Check the named agent in your configuration before running. ``--local`` is an
explicit acknowledgement of host execution, not a security feature. The runner
prints progress to stderr and the JSON report to stdout. It validates the
bundled fixture and scoring hashes and uses a fresh temporary copy for each
case. Normal and handled-error cleanup is best effort; a crash or force-stop
can leave files or processes behind. Existing step, wall-time, and command
limits apply, but wall time is checked between agent steps and cannot forcibly
interrupt a blocked model call or remote work.

The report records total input and output tokens only when the agent's model
reported usage for every model call of the run; any missing call leaves that
total null. Cost remains null unless a real implementation provides it. If any
case ends with an infrastructure error, the report is still saved and printed,
a warning is written to stderr, and the command exits nonzero. Coding failures
and pending review findings are report-only quality outcomes and still exit
zero.

Coding cases execute the fixed check locally and report pass or fail. Review
findings and the expected defect are saved in the private report with a
``pending_human_review`` outcome; a person must judge the findings. Agent and
check execution failures are infrastructure errors. Reports retain separate
outcome counts. Trace capture is optional; there is no quality gate or
automatic human judgment. Human judgments can be recorded separately without
changing the original run:

.. code-block:: bash

   workshop benchmark review RUN_ID --case CASE_ID --decision pass \\
     --reviewer "Reviewer name" --rationale "Defect identified accurately" \\
     --storage "$HOME/private-benchmarks"
   workshop benchmark report RUN_ID --storage "$HOME/private-benchmarks"

Decisions can be ``pass``, ``fail``, or ``inconclusive``. Each is stored as a
separate private record linked to the run, case version, and suite hash. Reports
show the full judgment history and separate counts based on the most recent
recorded decision per case; cases without decisions remain pending. The original
outcomes and counts remain unchanged. Reviewer identity is self-declared; these
local records are not authenticated or tamper-proof.

Trace capture
-------------

Add ``--trace`` to ``workshop benchmark run`` to request a private trajectory
collection in the same storage directory as the report. The report links the
collection by format, SHA-256, and storage key. ``workshop benchmark trace
RUN_ID --storage DIRECTORY`` displays it after checking the hash. The hash
checks consistency, not authenticity against someone who can modify both
files.

Each case has ``capture_status`` of ``captured`` or ``unavailable``. A failed
agent may not return a trajectory; it is not replaced with another case's data.
Captured records wrap agent-produced ``mini-swe-agent-1.1`` trajectories as
``workshop-benchmark-trace-1``. Existing records from earlier versions may lack
``capture_status``.

**Trajectories are not redacted or encrypted.** They can contain tasks, tool
calls and output, model responses, and serialized agent, model, and environment
configuration, including credentials supplied there. Do not assume secrets are
removed. Without ``--trace``, benchmark execution does not serialize agent
trajectories. A hard interruption can leave no report or trace; normal workspace
cleanup remains best effort.

Trace review with a local model
-------------------------------

**Experimental: the reviewer is not network-isolated and has not been
verified to stay local. Use only synthetic or non-sensitive traces.** A
registered model or local endpoint could forward data elsewhere; proxy settings
are not a security boundary. Do not use sensitive traces until the transport and
boundary are
independently verified. See ``docs/agent-trace-review-design.md``.

Register a small model served by ``llama-server`` on ``127.0.0.1`` in ``llm``
(for example in ``extra-openai-models.yaml``), then define a named reviewer
agent with ``model.protocol: native``, **no tools, and no MCP servers**:

.. code-block:: yaml

   version: 1
   agents:
     reviewer:
       model:
         model_name: local-reviewer
         protocol: native

The reviewer makes a model query, not an agent tool loop. Trace content is
passed between ``<trace>`` markers with instructions to treat it as untrusted
data. This prompt is not a guarantee against prompt injection. The prototype
requests a JSON observations list; it does not automatically create proposals.

.. code-block:: bash

   workshop eval review-trace RUN_ID \\
     --agent reviewer --storage "$HOME/private-benchmarks"
   workshop eval inspect TRACE_REVIEW_ID --storage "$HOME/private-benchmarks"
   workshop eval proposals --storage "$HOME/private-benchmarks"

``review-trace`` checks the registered model's reported base hostname, rejects
configured tools and MCP servers, and checks the trace's hash. These checks do
not establish where data ultimately goes. The model is separately constructed
after validation, and the loopback service or model plugin could forward data.
Long traces are truncated by serialized text position; truncation is recorded,
but individual case submissions may be omitted. Output that is not the required
JSON is stored as a failed review. If the model query itself raises an exception,
the command reports the error without storing a review record.

From a completed review, a person can record descriptive proposals linked to
specific observations and decide on them:

.. code-block:: bash

   workshop eval propose TRACE_REVIEW_ID --kind prompt-change \\
     --observation 0 --rationale "..." --payload '{"suggested_change": "..."}' \\
     --storage "$HOME/private-benchmarks"
   workshop eval decide PROPOSAL_ID --decision reject \\
     --reviewer "Name" --rationale "..." --storage "$HOME/private-benchmarks"

Kinds are ``eval-case``, ``prompt-change``, and ``skill-note``. Decisions are
``accept``, ``reject``, and ``revise``, stored as append-only history; the
latest decision is reported. **Nothing is ever applied automatically**:
proposals are records, and promotion to a versioned suite or prompt change is
a separate future action. The reviewer sets proxy environment variables during
the query, but libraries and processes may ignore or bypass them. The opt-in
probe below has not been run with a real ``llama-server`` and, even if it
passes, demonstrates only its particular client requests—not network isolation:

.. code-block:: bash

   WORKSHOP_TRACE_REVIEW_PROBE=1 \\
   WORKSHOP_TRACE_REVIEW_CONFIG=reviewer.yaml \\
   WORKSHOP_TRACE_REVIEW_AGENT=reviewer \\
     pipenv run pytest tests/test_trace_review_live.py

Comparing runs
--------------

Two stored runs of the same suite version can be compared:

.. code-block:: bash

   workshop benchmark compare RUN_ID_A RUN_ID_B \\
     --storage "$HOME/private-benchmarks"

The comparison shows per-case outcomes and diagnostics for each run, which cases
changed outcome, and each run's reported usage totals and review counts. It
requires matching suite IDs and hashes. A missing case in one run is shown with
a null outcome and counts as changed. A case is marked changed only when its
outcome differs; changes to findings or human decisions alone do not change that
flag. The comparison is descriptive: it contains no overall verdict, pass rate,
or quality score, and pending or infrastructure outcomes are never treated as
passes or failures.

An optional live smoke test runs the review suite using a configured agent;
this can contact a remote provider and execute configured tools:

.. code-block:: bash

   WORKSHOP_BENCHMARK_LIVE=1 \\
   WORKSHOP_BENCHMARK_AGENT_CONFIG=workshop.yaml \\
   WORKSHOP_BENCHMARK_AGENT_NAME=reviewer \\
     pipenv run pytest tests/test_local_benchmark_live.py

The coding smoke test also requires explicit opt-in and a named coding agent:

.. code-block:: bash

   WORKSHOP_BENCHMARK_CODING_LIVE=1 \\
   WORKSHOP_BENCHMARK_CODING_CONFIG=/path/to/workshop.yaml \\
   WORKSHOP_BENCHMARK_CODING_AGENT=coder \\
     pipenv run pytest tests/test_local_benchmark_live.py

Contracts
---------

The Python APIs are ``workshop.agent_benchmark.contracts`` and
``workshop.agent_eval.contracts``. Their Pydantic models reject unknown fields;
all have ``schema_version: 1``. Use ``model_validate_json()`` to validate JSON,
``model_dump(mode="json")`` for serializable data, and
``model_json_schema()`` for the full machine-readable schema. These schemas
and the local runner are experimental and may change.

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
redaction claims, or results. Separate experimental contracts exist for human
review decisions, trace reviews, proposals, and proposal decisions. They do not
make records tamper-proof or verify that model observations are correct.
Complete prompt/config fingerprints and run timestamps remain future work.

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
security review remain unverified. Sandbox ``ready`` is deliberately always
false; the local benchmark is a separate, explicitly unisolated mode, not a
sandbox override or fallback. For example:

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
