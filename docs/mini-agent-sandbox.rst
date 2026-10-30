Mini-SWE-agent and container sandboxes
======================================

`mini-SWE-agent <https://github.com/SWE-agent/mini-swe-agent>`_ is a small
software engineering agent. Its agent loop asks a model for actions and sends
shell commands to an execution environment. The environment returns command
output and status, and the agent includes those observations in subsequent
model requests. The project supplies local and Docker environments, among
others. See the `control flow <https://mini-swe-agent.com/latest/advanced/control_flow/>`_
and `environment cookbook <https://mini-swe-agent.com/latest/advanced/cookbook/>`_.

The workshop has a mini-SWE-agent-inspired coding agent with local and Docker
execution; see :doc:`agent`. It does not provide the hardened Testcontainers
sandbox described below. ``testcontainers`` is listed in the workshop's
``Pipfile``. This design is not an implemented or security-certified sandbox.

What each component does
------------------------

* **Agent:** mini-SWE-agent coordinates model requests, actions, observations,
  limits and the final result. Its default local environment executes commands
  on the host, so it is not an isolation boundary.
* **Model:** a configured model supplies actions. It may run locally or through
  an external provider. External providers receive the task, command output
  and other context sent to the model.
* **Testcontainers:** starts and stops a container through the Docker daemon.
  It can provide a disposable execution environment, but does not itself make
  untrusted code safe.
* **Environment adapter:** workshop code would translate mini-SWE-agent action
  dictionaries into container executions and return their output and status.

Mini-SWE-agent already has a Docker environment that creates its own
container. Testcontainers would be an alternative lifecycle manager, not an
extra layer around that environment. Connecting the two requires a custom
adapter because the built-in Docker environment starts its own container.

Try an isolated command
-----------------------

With Docker running and workshop dependencies installed, run this from the
repository root. Docker may download the image on first use. This demonstrates
container lifecycle and command execution, not an agent:

.. code-block:: shell

   pipenv run python - <<'PY'
   from testcontainers.core.container import DockerContainer

   sandbox = DockerContainer(
       "python:3.12-slim",
       command="sleep 120",
       network_mode="none",
       user="65534:65534",
       read_only=True,
       cap_drop=["ALL"],
       security_opt=["no-new-privileges:true"],
       mem_limit="512m",
       pids_limit=128,
   ).with_tmpfs_mount("/tmp", "size=64m,mode=1777,nosuid,nodev")

   with sandbox:
       result = sandbox.exec(["bash", "-c", "cd /tmp && printf sandbox-ok"])
       print(result.exit_code, result.output.decode("utf-8", errors="replace"))
   PY

The expected output includes ``0 sandbox-ok``. The context manager stops the
container when the block exits. Its writable temporary filesystem is discarded.
The exact tmpfs option string above was verified with the workshop's installed
Testcontainers version and Docker; check compatibility when upgrading.

Build an agent environment
--------------------------

A future integration can follow this lifecycle:

1. Prepare a disposable workspace from an explicitly selected source revision.
   Copy only required files into the container. Do not mount the user's live
   checkout or Docker socket. Avoid copying credentials, Git configuration,
   environment files or caches.
2. Start one container per agent run using Testcontainers. Use a reviewed,
   pinned image containing Bash and the project's required tools. Keep the model
   client and provider credentials on the host; do not forward them into the
   container. Set a fixed working directory inside the workspace.
3. Implement mini-SWE-agent's ``Environment`` protocol. Its ``execute(action,
   cwd)`` method receives an action dictionary and returns a result with
   ``output`` and ``returncode``. Implement ``get_template_vars`` and
   ``serialize`` as required by the protocol. Preserve mini-SWE-agent's
   submission behavior as well as its error and timeout conventions; use the
   `Docker environment implementation <https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/docker.py>`_
   as the reference for the version being integrated.
4. Execute each action with a new Bash process in the same container. Files
   persist for the run, but shell variables and the current directory do not
   persist across commands unless explicitly managed. Capture combined output,
   exit status and errors, and enforce output and execution limits.
5. Construct a mini-SWE-agent with the adapter and a model, set step, cost and
   wall-time limits, and run the task. See the upstream `Python bindings
   <https://mini-swe-agent.com/latest/usage/python_bindings/>`_ for the agent
   configuration required by the version in use.
6. Before stopping the container, extract a bounded patch and any approved
   artifacts into a separate staging area. Treat all output as untrusted. Review
   the patch and run independent checks before applying it to a host checkout.
   On completion, failure or cancellation, stop and remove the container.

The sample uses an empty writable ``/tmp`` rather than a source workspace.
An implementation must also decide how to transfer a workspace and artifacts,
limit their size, and handle binary files, symlinks and interrupted runs.
Network isolation prevents package downloads inside the sandbox, so bake needed
packages into the image or provide a separately reviewed dependency strategy.

Security boundaries and verification
------------------------------------

Containers share a kernel with their Docker host or Docker virtual machine;
they are not equivalent to a dedicated VM. The example reduces privileges but
is not a guarantee against container escape, kernel vulnerabilities, resource
exhaustion or malicious output. The Docker daemon and image are trusted parts
of this setup. Pulling images, model calls and Testcontainers' helper containers
are outside the agent container's network setting.

Before using this for untrusted work, test that the chosen Docker runtime
actually enforces its restrictions: no network, no host mounts or secrets,
non-root execution, read-only root, memory and process limits. Add CPU, disk,
output-size and wall-clock limits appropriate to the workload. A host-side
request timeout alone may leave a container process running; explicitly kill
and verify termination on timeout. Test cleanup on errors and interruption,
and use a stronger isolation boundary such as a disposable VM when the risk
requires it. Do not let model instructions override these controls.

Sources: `mini-SWE-agent <https://github.com/SWE-agent/mini-swe-agent>`_,
`Testcontainers core <https://testcontainers-python.readthedocs.io/en/latest/core/README.html>`_,
and the `Docker security documentation <https://docs.docker.com/engine/security/>`_.
