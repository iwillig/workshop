Coding agent
============

The workshop coding agent asks an ``llm`` model for shell commands, runs
those commands, and sends their output back to the model. It continues until
the model submits a result or a configured limit stops the run. The default
interactive agent asks for approval before each command.

Before you run it
-----------------

Install the workshop and activate its environment as described in
``research_context/readme.md``. Configure a model supported by the installed
`LLM library <https://llm.datasette.io/>`_. A provider may require an API key
or an additional LLM plugin. Use ``llm models list`` to see available model
IDs and ``llm keys`` for provider key management. Check the provider's setup
instructions before use. The model receives the task and command observations;
an external provider can receive data from the workspace.

**Local execution is not a sandbox.** Commands run with your user's permissions
and inherit the host environment, which may contain credentials. Review every
command and use a disposable workspace without secrets. Approval is not a
security boundary: a command you approve can make changes or disclose data.

Run a task
----------

Start with a small task in a disposable directory:

.. code-block:: shell

   workshop agent run --task 'List the files in this directory and summarize them.' \
     --cwd /path/to/disposable-workspace --step-limit 10 \
     --output /path/to/run.traj.json

The default model is the LLM library's configured default. Add ``--model
MODEL_ID`` to select another installed model. The task and workspace path are
examples; replace them with values appropriate for your machine. The agent
prints the model response and asks whether to run each command. Press Enter to
approve, or type feedback and press Enter to reject it. The feedback is sent
back to the model. Review the resulting files and run independent tests before
using the output.

Each command runs in a new shell process. File changes persist in the workspace,
but shell variables and changes to the current directory do not persist between
commands. The CLI prints an exit status and any final submission. A status of
``Submitted`` indicates that the agent submitted, not that its work is correct.
``LimitsExceeded``, ``TimeExceeded``, and ``RepeatedFormatError`` indicate that
a limit or repeated formatting errors stopped the run.

The optional output file contains JSON messages, configuration, model usage,
and exit information. It is updated during the run and overwritten if it
already exists. It can contain tasks, commands, output, and configuration values,
including secrets; store it securely and review it before sharing.

Command options
---------------

``workshop agent run --help`` lists the options. Values supplied on the command
line override the corresponding YAML configuration values.

* ``-t, --task TEXT``: required task for the agent.
* ``-c, --config PATH``: YAML configuration file; the packaged default is used
  when omitted.
* ``-m, --model MODEL_ID``: LLM model ID or alias.
* ``-y, --yolo``: run commands without confirmation. Do not use this on an
  untrusted task or workspace.
* ``-o, --output PATH``: save the trajectory as JSON.
* ``--cwd PATH``: command working directory. With Docker, this path is inside
  the container, not on the host.
* ``--image IMAGE``: use the Docker environment with this image.
* ``--step-limit N``: maximum number of model calls; zero disables the limit.
* ``--timeout SECONDS``: timeout for each command.

Configuration and limits
------------------------

The packaged configuration is ``workshop/agent/configs/default.yaml``. Copy it
to a local file and pass that file with ``--config`` to change settings. The
three sections select the agent, execution environment, and model. For example:

.. code-block:: yaml

   agent:
     agent_class: interactive
     mode: confirm
     step_limit: 10
     wall_time_limit_seconds: 300
     cost_limit: 1.0
   environment:
     environment_class: local
     cwd: /path/to/disposable-workspace
     timeout: 30
   model:
     model_class: llm
     model_name: null
     input_cost_per_mtok: 0.0
     output_cost_per_mtok: 0.0

The packaged configuration sets a 50-call limit and a 30-second command timeout.
The agent also defaults to a cost limit of 3.0, no wall-time limit, and three
consecutive format errors. Limits are checked between model calls; they do not
interrupt a model call or a command already in progress. The command timeout is
separate. A zero step, cost, wall-time, or format-error limit disables that
limit. Cost is calculated from reported token usage and the configured prices
per million tokens. Prices default to zero, so the cost limit cannot control
spending unless prices and usage are available. Check provider billing separately.

The default agent uses Jinja prompt templates and expects exactly one fenced
``mswea_bash_command`` block per response. Model and agent configuration can
override the prompt templates. A model that does not follow this format may
stop the run after repeated format errors.

Docker execution
----------------

With Docker running, an image containing ``sleep`` and Bash can run commands in
a container instead of directly on the host:

.. code-block:: shell

   workshop agent run --task 'List the files in the container.' \
     --image python:3.12-slim --step-limit 10

The agent starts a container and uses it for the run. No host workspace is
mounted or copied by default, and container files are not automatically copied
back. ``--cwd`` names a directory inside the container; it must exist. The
container environment is not a hardened sandbox: network access and other
Docker defaults apply, and a command timeout does not guarantee that the
container process has stopped. Container cleanup is attempted after use, but
verify and remove leftover containers if necessary. See
``docs/mini-agent-sandbox.rst`` for the separate proposed hardened sandbox.

To enable unattended execution, ``--yolo`` skips approval. It does not add
isolation or restrictions. Use it only where the execution environment and
consequences are acceptable.
