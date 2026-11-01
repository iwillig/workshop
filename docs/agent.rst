Coding agent
============

The workshop coding agent uses an ``llm`` model to work on a task. In the
default shell protocol, it asks the model for shell commands and sends their
output back. The optional native protocol lets a tool-capable model call
built-in tools and configured MCP servers. A run ends when the model submits a
result or a configured limit stops it.

The default interactive agent displays concise tool progress and runs actions without
asking for approval. In a POSIX terminal it uses an inline Textual view showing
activity, elapsed time, and reported token usage. Runs are foreground processes;
managed background jobs are not implemented.

Subsystems
----------

The agent system is organized as sibling Python packages:

* ``workshop.agent`` contains the existing LLM-based agent, model and execution
  environments, built-in tools, and MCP integration.
* ``workshop.agent_config`` loads named or legacy YAML configurations and
  builds agents. Configuration loading does not require constructing an agent.
  Existing ``workshop.agent.config`` imports remain available for compatibility.
* ``workshop.agent_benchmark`` is a placeholder for benchmark suites and runs.
* ``workshop.agent_eval`` is a placeholder for evaluations and trace review.

The benchmark and evaluation packages do not yet provide runners or APIs.

Project configuration
---------------------

``workshop.yaml`` holds project-wide settings and is separate from agent
configuration files. The CLI searches the current directory and its parents
for the nearest ``workshop.yaml``. Use ``workshop --workshop-config PATH`` to
select another file explicitly. Missing configuration uses defaults; invalid
configuration fails. Relative paths in this file resolve from its directory.

Agent model-call logging is disabled by default. To enable it explicitly:

.. code-block:: yaml

   llm:
     logging:
       enabled: true
       database: .workshop/logs.db

The repository's ``workshop.yaml`` shows these settings with logging disabled,
and ``.workshop/`` is ignored by Git. When enabled, completed model responses
are recorded using LLM's SQLite logging API. Records can include system and user
prompts, workspace contents, tool calls and results, model responses, usage and
provider metadata. Tool results are normally recorded in the next completed
model response, so interrupted or failed runs can have incomplete logs.
Logging errors fail the run; a model request may already have completed before
an error is detected. Forced interruption may also leave incomplete records.
This setting does not control standalone ``llm`` CLI logging or provider
retention, and does not move existing logs. Inspect this database with
``llm logs list --database PATH``.

New database files are created with owner-only permissions; on POSIX an existing
file with group or other access is rejected. New final parent directories are
created with owner-only permissions. Use a trusted private directory, check
permissions on existing and intermediate directories, and protect backups and
SQLite sidecar files. Logging is not supported for arbitrary custom models
unless they implement the workshop logging configuration interface. The optional
trajectory output is separate and remains subject to its own privacy risks.

Before you run it
-----------------

From the repository root, install the dependencies and the workshop command:

.. code-block:: shell

   pipenv sync
   pipenv run pip install -e .
   pipenv run workshop agent run --help

The project requires Python 3.15 as specified in ``Pipfile``. Either prefix
commands below with ``pipenv run`` or activate the environment with
``pipenv shell``. Research service tokens are not required to run the agent.

Configure a model supported by the installed `LLM library
<https://llm.datasette.io/>`_. A provider may require an API key or an
additional LLM plugin. Use ``pipenv run llm models list`` to see available
model IDs and ``pipenv run llm keys`` for provider key management. Check the
provider's setup instructions before use. The model receives the task and tool
observations; an external provider can receive data from the workspace.

**Local execution is not a sandbox.** Commands run without confirmation, with
your user's permissions, and inherit the host environment, which may contain
credentials. Commands can modify files or disclose data. Use a disposable
workspace without secrets.

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
prints tool progress and runs commands without prompting. It prints the final
submission once when the run finishes. Review the resulting files and run
independent tests before using the output.

The CLI exits with status zero only when the agent submits a result; limits and
other non-submission outcomes produce a nonzero exit status.

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
line override the corresponding YAML configuration values. Use ``--agent NAME``
to select an agent from a named configuration file.

* ``-t, --task TEXT``: required task for the agent.
* ``-c, --config PATH``: YAML configuration file; the packaged default is used
  when omitted.
* ``--agent NAME``: select a named definition from the YAML configuration.
* ``--no-live``: use plain progress output rather than the Textual view.
* ``-m, --model MODEL_ID``: LLM model ID or alias.
* ``-y, --yolo``: deprecated compatibility flag; commands already run without confirmation.
* ``-o, --output PATH``: save the trajectory as JSON.
* ``--cwd PATH``: command working directory. With Docker, this path is inside
  the container, not on the host.
* ``--image IMAGE``: use the Docker environment with this image.
* ``--step-limit N``: maximum number of model calls; zero disables the limit.
* ``--timeout SECONDS``: timeout for each command.

Configuration and limits
------------------------

The packaged configuration is ``workshop/agent_config/configs/default.yaml``. Copy it
to a local file and pass that file with ``--config`` to change settings. The
three sections select the agent, execution environment, and model. For example:

.. code-block:: yaml

   agent:
     agent_class: interactive
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

The agent scheduler accepts ``agent.parallel_tools`` (a list of tool names) and
``agent.max_parallel_tools`` (a positive integer, default 4). Calls are serial
by default. Consecutive calls whose ``tool`` names are listed may run concurrently;
other calls are serial barriers, and results retain request order. Only mark a
tool parallel-safe if overlapping it with other listed tools is acceptable:
concurrent writes and commands can race. The fenced-shell protocol produces
only one action at a time. Native tool-call batches can use these settings.

Tool output sent to the model is limited to approximately 50,000 characters.
Local and Docker command output is drained with bounded in-memory capture, and
the read tool reads files in bounded chunks. MCP results are truncated during JSON
serialization, with a marker when incomplete; truncated results may not be valid
JSON. The MCP SDK still receives and parses complete responses, and individual
serialized values may be large. Docker startup and cleanup output are not
covered by the command-output limit. These limits do not bound transport or
server memory.

The packaged configuration sets a 50-call limit and a 30-second command timeout.
The agent also defaults to a cost limit of 3.0, no wall-time limit, and three
consecutive format errors. Limits are checked between model calls; they do not
interrupt a model call or a command already in progress. The command timeout is
separate. A zero step, cost, wall-time, or format-error limit disables that
limit. Cost is calculated from reported token usage and the configured prices
per million tokens. Prices default to zero, so the cost limit cannot control
spending unless prices and usage are available. Check provider billing separately.

The default shell protocol uses Jinja prompt templates and expects exactly one
fenced ``mswea_bash_command`` block per response. Model and agent configuration
can override the prompt templates. A model that does not follow this format may
stop the run after repeated format errors. An opt-in native tool-call protocol
is available for MCP servers, as described below.

To keep the system prompt in a separate UTF-8 file, set
``agent.system_template_path`` in the YAML configuration:

.. code-block:: yaml

   agent:
     agent_class: interactive
     system_template_path: prompts/system.txt

Relative paths are resolved from the directory containing the YAML file;
absolute paths are also supported. The file is rendered as a Jinja template
when the agent starts, just like an inline ``system_template``. Set only one
of ``system_template`` and ``system_template_path``. Prompt templates are
trusted configuration: template variables can include host environment values,
which may be sent to the model if referenced.

Live model tests
----------------

``tests/test_agent_model_live.py`` sends test prompts to the team's Hugging Face
OpenAI-compatible endpoint using ``unsloth/Qwen3.8-27B-GGUF``. Set ``HF_TOKEN``
in the environment before running the test suite; do not put the token in the
repository. These tests require network access and a running, authorized
endpoint, and may incur inference costs. They fail if the token is missing.

.. code-block:: shell

   pipenv run python -m pytest tests/test_agent_model_live.py

MCP servers
-----------

The native protocol can discover MCP tools over stdio or Streamable HTTP. Define
servers in the configuration and select a model that supports native tool
calls. For example:

.. code-block:: yaml

   model:
     model_class: llm
     model_name: your-tool-capable-model
     protocol: native
   mcp_servers:
     local:
       transport: stdio
       command: python
       args: ["/path/to/server.py"]
     remote:
       transport: http
       url: https://example.com/mcp
       headers_env:
         Authorization: MCP_AUTH_HEADER

Run the agent with ``workshop agent run --config agent.yaml --task '...'``.
Server tools are named ``mcp__SERVER__TOOL``. Each server also provides
``list_resources``, ``read_resource``, ``list_prompts``, and ``get_prompt``
tools with the same prefix. Sessions open at the start of a run and close when
it ends. The final model response is the submission. Tool results and server
errors are sent to the model; trajectories may contain sensitive data.

Native mode also provides these built-in tools to the model:

* ``read`` reads a UTF-8 file. Its optional ``offset`` and ``limit`` are
  positive line numbers/counts; the defaults are line 1 and 2,000 lines.
* ``edit`` replaces a nonempty ``old_text`` with ``new_text`` only when the
  old text occurs exactly once in an existing UTF-8 file.
* ``bash`` runs a command in the configured local or Docker environment.

Read and edit resolve paths within the local workspace and reject paths that
resolve outside it. They are not yet available for Docker environments. Bash
is not restricted to the workspace. The model, not the CLI user, supplies tool
arguments during a run.

``headers_env`` maps HTTP header names to environment-variable names. For the
example above, set ``MCP_AUTH_HEADER`` to the complete authorization value,
such as ``Bearer ...``. Missing variables cause connection setup to fail. Use
HTTPS for credentials; OAuth is not yet supported. Configure only trusted
servers: stdio servers execute local programs, remote
servers receive tool arguments, and tool calls run without approval. Tool
responses are untrusted data and may contain instructions or sensitive content.

Named agents
------------

A YAML file may define multiple agents. For example, create ``agents.yaml``
and replace the model ID and workspace paths with values from your environment:

.. code-block:: shell

   mkdir -p prompts
   printf '%s\n' 'Review code. Report findings without modifying files.' > prompts/reviewer.txt

Then add these definitions to ``agents.yaml``:

.. code-block:: yaml

   agents:
     reviewer:
       model:
         protocol: native
         model_name: your-tool-capable-model
       prompts:
         system_file: prompts/reviewer.txt
       environment:
         environment_class: local
         cwd: /path/to/workspace
       limits:
         step_limit: 20
       tools:
         read: {}
     coder:
       model:
         protocol: native
         model_name: your-tool-capable-model
       environment:
         environment_class: local
         cwd: /path/to/workspace
       tools:
         read: {}
         edit: {}
         bash: {}

.. code-block:: shell

   workshop agent run --config agents.yaml --agent reviewer --task 'Review the code'

``prompts.system_file`` resolves relative to the YAML file; ``prompts.system``
and ``prompts.instance`` provide inline templates. ``limits`` accepts agent
configuration fields such as ``step_limit``. ``tools`` selects built-in native
tools; omit it to use all available built-ins. Per-tool options are not yet
supported. Selecting only ``read`` restricts the built-in tools; configured MCP
server tools are separate and are still exposed. MCP servers can be configured
within an agent using ``mcp_servers``. Legacy single-agent files remain
supported without ``--agent``. Supplying ``--agent`` is required for named
files. These commands run in the foreground; managed background jobs are not
yet implemented.

For example, choose the coder and override its model-call limit for one run:

.. code-block:: shell

   workshop agent run --config agents.yaml --agent coder --step-limit 5 \\
     --task 'Fix the failing test and explain the change.'

CLI overrides apply to the selected definition for that run; they do not edit
its YAML file.

Review this project
-------------------

The repository includes ``examples/review-agent.yaml``, a named agent that
exposes only the built-in read tool. From the repository root, run:

.. code-block:: shell

   just review-agent

The recipe prints concise tool progress, reported per-call and cumulative token
usage, and the complete final review to standard output; it does not print full
tool observations or save a trajectory. Missing usage is shown as unknown, and
cumulative totals are marked partial if a provider omits any counts. Totals sum
reported usage across calls, so repeated context contributes to input tokens.
Tool and token progress are each limited to 30 lines per run in plain output.
The Textual view keeps the eight most recent tool calls visible while it updates
activity, a bounded snippet of the latest model output, the total number of tool
calls started, and elapsed time. The snippet is labeled ``reasoning`` when the
provider reports reasoning, otherwise ``response``; it is a display preview and
not a model-generated summary, and it may contain sensitive workspace data sent
to the model. Failed calls count as started calls; model requests do not. The
recent calls, total, and final snippet are printed after the view closes. Plain
output does not stream model snippets. Exact tokens are shown only after the provider reports them; no
streaming estimate is made. In the live view, Ctrl+C forcibly stops the supervised agent process and attempts
to terminate its local subprocesses. Docker container removal is attempted in
the background. The command exits with status 130. Changes and trajectories
may be incomplete, remote requests can continue, and cleanup is best-effort;
check for leftover containers or processes. For redirected output, non-POSIX
systems, or ``--no-live``, the CLI uses plain output and standard terminal
signal handling rather than this supervised stop. The final submission is printed
in full after the live view closes. To choose different files or save a trajectory, run the
underlying command directly:

.. code-block:: shell

   pipenv run workshop agent run --config examples/review-agent.yaml \\
     --agent reviewer \\
     --task 'Review workshop/agent/models.py and workshop/agent/default_agent.py for bugs. Report findings with file paths.' \\
     --output /tmp/workshop-review.traj.json

The example uses the ``hf-glm`` model ID, registered against Hugging Face's
shared Inference Providers router (``https://router.huggingface.co/v1``) serving
``zai-org/GLM-5.3-Flash``. Register an extra OpenAI model with ``llm`` using
that base URL and your Hugging Face key, set ``supports_tools: true``, and pass
``--model`` with another registered tool-capable model if you prefer. Hugging
Face may route requests to a third-party provider, so review content, including
read file contents, is sent there. The provider must be reachable and may
charge for use. GLM-5.3-Flash defaults to maximum reasoning effort, so runs may
be slower or costlier than smaller models.

Run from the repository root because the example's ``cwd: .`` is relative to
the process working directory, not the YAML file. The read tool cannot list
files or inspect Git diffs, so provide explicit file paths in the task. It does
not run tests or execute shell commands. Review the resulting findings yourself.

Although Bash, edit, and MCP tools are not enabled in this example, the model
can request any readable file within the workspace, including local secrets,
and send its contents to the model provider. Prompt instructions are not a
security boundary. For sensitive repositories, use a sanitized copy and a
trusted model; if you save a trajectory, store it securely.

Troubleshooting
---------------

* **Unknown model or missing API key:** check ``llm models list`` and the
  provider's setup instructions in the same Pipenv environment.
* **Named agent selection fails:** pass ``--agent NAME`` for a file with an
  ``agents`` mapping; omit it for a legacy single-agent file.
* **Repeated format errors:** the shell protocol requires a model response with
  exactly one ``mswea_bash_command`` block. Check the model and prompt; use
  ``model.protocol: native`` only with a model that supports native tool calls.
* **MCP connection fails:** check that the server is running, its transport and
  URL or command are correct, and any ``headers_env`` variables are set. A
  stdio server runs on the host; its command must be available there.
* **Read or edit is unavailable:** those built-ins require the local
  environment and an existing UTF-8 file whose resolved path is inside the
  workspace. Docker native mode exposes Bash, not read/edit.
* **A run hits a limit:** inspect its printed status and trajectory. Adjust the
  configured limit only if the additional execution and cost are acceptable.

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
container process has stopped. Cleanup waits for Docker to stop the container
and falls back to forced removal. Cleanup failures are reported separately from
the agent result or primary error. Abrupt process termination can still leave
containers behind; verify and remove leftovers if necessary. See
``docs/mini-agent-sandbox.rst`` for the separate proposed hardened sandbox.

Commands run unattended in both local and Docker environments. Use the agent
only where the execution environment and consequences are acceptable. Existing
configurations with ``mode: confirm`` must remove that setting; the agent refuses
to run them rather than silently removing their former confirmation behavior.
The legacy ``mode: yolo`` setting is still accepted.
