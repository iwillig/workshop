# Project configuration

Workshop searches the current directory and its parents for the nearest
`workshop.yaml`. Use `workshop --workshop-config PATH ...` to select a file
explicitly. `workshop config validate` reports the selected file and checks
project configuration without connecting to a model or starting tools.
`workshop config show` displays normalized configuration structure with scalar
values redacted; mapping keys, including agent names and environment variable
names, remain visible. A missing file uses built-in defaults.

```yaml
version: 1
default_agent: coding
git:
  base_ref: main
github:
  repositories:
    app: example-owner/example-repo
  default_repo: app
llm:
  logging:
    enabled: false
    database: .workshop/logs.db
benchmark:
  storage: .workshop/benchmarks
  suite: coding-v1
evaluation:
  budget: 10
browser:
  width: 1280
  height: 800
agents:
  coding:
    model:
      model_name: example-model-id
      protocol: native
    environment:
      environment_class: local
      timeout: 30
    limits:
      step_limit: 50
    prompts:
      system_file: prompts/coding.md
    tools:
      read: {}
      edit: {}
      bash: {}
```

Use an installed `llm` model ID and configure its API token outside YAML.
Project-defined agents require an explicit `model_name` or, for an agent run,
`--model`. Command-line flags override YAML for a single invocation. Select an agent with `--agent` or
set `default_agent`. A project file is not a security boundary: agents can run
commands with your permissions and models and MCP servers can receive data.
Only load trusted configuration and prompt files.

Prompt files, the log database, and benchmark storage paths resolve relative to
the YAML file. The agent execution directory defaults to the invocation
directory; `environment.cwd` and `--cwd` control it (Docker paths refer to the
container). CLI-provided paths retain their normal invocation-relative meaning.
`benchmark.storage` supplies the default for benchmark and evaluation storage
commands; `benchmark.suite` supplies the benchmark run default. A benchmark
still requires the explicit `--local` safety acknowledgement. Trace capture
is opt-in with `--trace`. Logging is opt-in and can contain sensitive workspace
and model data; keep the database, reports, and traces private.

## Local branch review and GitHub defaults

`git.base_ref` is a project-wide local Git ref used by the experimental
`branch-reviewer`. Set it to the branch or commit you want to compare against;
Workshop resolves it locally and does not fetch updates. The reviewer compares
the merge base to the captured current-branch HEAD. Staged, unstaged, and
untracked changes are excluded. From the repository root, run:

```sh
workshop agent run --agent branch-reviewer --task "Review my current branch"
```

The checked-in agent is an example: other projects must define their own named
agent and explicitly select `git_review_context`, `git_review_diff`,
`git_read_file`, and `git_search`. These native tools require a local execution
environment and a configured `git.base_ref`. See the [agent guide](agent.rst)
for usage, coverage limitations, and trust considerations.

`github.repositories` maps local aliases to GitHub `OWNER/REPO` identifiers;
`github.default_repo` names one of those aliases. GitHub commands and native
GitHub tools use it when no repository is supplied. An explicit alias or
`OWNER/REPO` takes precedence. For example:

```sh
workshop research-context github get-pr 123
workshop research-context github get-pr app 123
workshop research-context github get-pr another-owner/another-repo 123
```

The standalone `research-context` CLI also discovers the nearest project file
and accepts `--workshop-config PATH`. General GitHub search queries are not
implicitly restricted to the default repository. Credentials remain outside
`workshop.yaml`.

## Credentials and integrations

Never put API tokens in YAML, prompt files, model options, command arguments,
URLs, or MCP `env`: these may be serialized, logged, or shared. Set provider
credentials through the provider's documented environment variables or `llm`
key store. Asana, Notion and GitHub use `ASANA_ACCESS_TOKEN`, `NOTION_TOKEN`
and `GITHUB_TOKEN`; research commands also load `.env.local` in the invocation
directory, without overriding existing environment variables. Keep that file
out of version control.

HTTP MCP servers accept `headers_env`, mapping header names to environment
variable names. Stdio servers accept `env_from`, mapping child environment
names to environment variable names; values are read when connecting, not when
loading the project file. Non-secret stdio environment values belong in `env`:

```yaml
version: 1
agents:
  coding:
    model: {model_name: example-model-id, protocol: native}
    mcp_servers:
      example:
        transport: stdio
        command: example-mcp
        env: {MODE: read}
        env_from: {API_TOKEN: EXAMPLE_API_TOKEN}
```

HTTP `headers_env` passes the value verbatim, so include any `Bearer ` prefix
in the environment value. Missing referenced values fail the connection.
Local commands inherit the host environment and may access secrets; Docker
commands receive configured `env` and `forward_env`. Treat model output,
trajectories and subprocess output as potentially sensitive.

## Boundaries

Built-in agent, model and environment fields and MCP transport structure are
validated before use. Model-provider-specific `model_options`, custom dotted
classes, their options, and external `llm` plugins cannot be fully validated by
Workshop. Plugins can have their own installation, configuration, and defaults;
Workshop does not control those external tools. Set the model ID and relevant
model options explicitly in the project configuration for reproducibility.
Workshop does not read `WORKSHOP_DOCKER_EXECUTABLE`; set a Docker agent's
`environment.executable` instead. The loopback-only GitHub endpoint override is
an internal benchmark fixture mechanism, not project configuration.

Agent definitions must appear under `agents` in project configuration; separate
agent configuration files are not supported. The distribution is named
`llm-workshop` and requires Python 3.15. After publication, install it with
`python -m pip install llm-workshop`. The `workshop` and `ai-workshop` names on
PyPI belong to other projects. See `docs/publishing.md` for release setup.
