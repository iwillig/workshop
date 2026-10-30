# mini-swe-agent

Research notes on [mini-swe-agent](https://mini-swe-agent.com/latest/) (v2, from the [SWE-agent/SWE-bench team](https://github.com/SWE-agent/mini-swe-agent)) and how to use it correctly for coding agents. Compiled 2026-10-30 from the official documentation; sources are linked inline.

## Summary

mini-swe-agent is a deliberately minimal coding agent: ~100 lines of core Python, **bash as the only tool**, no use of the model's tool-calling interface, strictly **linear message history**, and every action run as an **independent `subprocess.run`** call rather than a persistent shell. Despite the minimalism it scores above 74% on SWE-bench Verified (with Gemini 3 Pro), so the architecture is not a toy.

The correct way to use it depends on the job:

- **Interactive local use:** the `mini` CLI with confirm mode (review each command before it runs).
- **As a library for building coding agents:** the Python bindings — pick an agent class, model class, and environment class, wire them in a run script, and customize by subclassing two hooks (`execute_actions` on the agent, `execute` on the environment).
- **Sandboxed or batch runs (SWE-bench style):** Docker/Podman environments, YAML configs, trajectory files out.
- **Fine-tuning / RL:** the linear history means the trajectory *is* the prompt, which is the main reason the project exists — training data without scaffold-specific history surgery.

It is the wrong tool when you need custom tools with their own interfaces, non-linear history processing, or persistent shell state; the [FAQ](https://mini-swe-agent.com/latest/faq/) points those cases to full SWE-agent.

## Design philosophy and why it matters

The [front page](https://mini-swe-agent.com/latest/) names four commitments, each with a practical consequence:

1. **Bash only, no tool-calling API.** Works with *any* model (including local ones) because nothing depends on provider-specific function-calling; nothing has to be installed in the execution environment.
2. **Linear history.** Each step appends messages; the trajectory equals the prompt. This makes debugging trivial (read the transcript top to bottom) and makes trajectories directly usable for fine-tuning or RL without reconstructing what the model actually saw.
3. **Independent actions via `subprocess.run`.** No persistent shell session. The [FAQ](https://mini-swe-agent.com/latest/faq/) gives three reasons: with a persistent shell it is hard to tell when a command finished, a bad command can kill the session, and interrupting can corrupt shell state. The trade-off: `cd` and `export` do not persist between steps (the model must prefix commands; per-action env vars still work). Sandboxing becomes trivial — execution is one function that can be swapped for `docker exec`.
4. **Hackable.** Small enough to read whole; extension is by subclassing, not plugins.

## Control flow (what the agent actually does)

From the [control flow page](https://mini-swe-agent.com/latest/advanced/control_flow/): `DefaultAgent.run(task)` renders two Jinja2 templates — `system_template` and `instance_template` — then loops on `step()` until a message with role `exit` appears. Each step is `query()` (check limits, call model, record cost, append reply) then `execute_actions()` (run each parsed action in the environment, append observation messages).

Termination and interruption are **exception-based**: the environment raises `Submitted` when command output starts with a magic string; `LimitsExceeded`, `FormatError`, timeouts, and `UserInterruption` all inherit from `InterruptAgentFlow` and carry the messages they add to the trajectory. Limits available in config: `step_limit` (model calls), `cost_limit` (default 3.0 dollars), `wall_time_limit_seconds`, and `max_consecutive_format_errors`.

Templates render with `StrictUndefined` (a missing variable is an error, not silence) and can reference config values, the task, `n_model_calls`, `model_cost`, and `elapsed_seconds` — so prompts can tell the model how much budget it has left.

## The `mini` CLI

From the [CLI page](https://mini-swe-agent.com/latest/usage/mini/): install via pip/pipx/uvx, run `mini -t "task"` (or get prompted). Three modes, switchable mid-run: **confirm** (`/c`, default — Enter runs the proposed command, typing a message rejects it), **yolo** (`/y` or `-y` — commands run immediately), and **human** (`/u` — you type the commands). Useful flags: `-c` config (note: specifying `-c` *replaces* the default config; `key=value` overrides like `-c model.model_kwargs.temperature=0.5` also work), `-m` model, `-l` cost limit (`-l 0` disables), `-o` trajectory output. Each run saves its full trajectory (default `last_mini_run.traj.json` in the config directory).

## Configuration

Two layers:

- **Global** ([docs](https://mini-swe-agent.com/latest/advanced/global_configuration/)): environment variables or a `.env` file, managed with `mini-extra config setup|set|unset|edit`. Key variables: `MSWEA_MODEL_NAME` (default model), API keys (`ANTHROPIC_API_KEY` etc.), `MSWEA_GLOBAL_COST_LIMIT` and `MSWEA_GLOBAL_CALL_LIMIT` (spend caps across all runs), `MSWEA_COST_TRACKING=ignore_errors` (for models litellm can't price — beware unmanaged spend), `LITELLM_MODEL_REGISTRY_PATH` (register custom/local models), `MSWEA_CONFIG_DIR`, `MSWEA_DEFAULT_RUN` (swap the CLI entry point for your own run script).
- **Per-agent YAML** ([docs](https://mini-swe-agent.com/latest/advanced/yaml_configuration/)): four top-level keys — `agent` (templates, limits, `agent_class`), `environment` (`environment_class`, `cwd`, `timeout`), `model` (`model_name`, `model_class`, `model_kwargs`, `action_regex`), `run` (output file). Actions are parsed from the model's text by `action_regex` (default: a markdown ```` ``` ```` block; an XML variant exists). If you change the regex, every template must teach the same format. Escaping tip from the docs: keep `action_regex` on one line without block scalars — a trailing newline breaks the match. Built-in configs load by name (e.g. `--config swebench_xml`).

## Environments and sandboxing

From the [environments page](https://mini-swe-agent.com/latest/advanced/environments/), selected with `--environment-class` or `environment.environment_class`:

| Environment | What it is | When to use |
| --- | --- | --- |
| `local` | `subprocess.run` on the host. **No isolation.** | Your own machine, trusted tasks only. CLI default. |
| `docker` | `docker exec` in a container | Default choice for isolated runs and benchmarks. |
| `singularity` | Singularity/Apptainer | HPC clusters without Docker. |
| `swerex_docker` / `swerex_modal` | Docker or Modal cloud via SWE-ReX | Large-scale/remote runs, agent training at scale. |
| `bubblewrap` | Unprivileged Linux sandbox | Lightweight isolation; experimental, Linux-only. |
| `contree` | ConTree hosted sandbox | Hosted, Git-like execution platform. |

Because an environment is just a class with one `execute(action, cwd) -> dict` method, writing a custom one (e.g. backed by Testcontainers, per our [Fedora bootc research](fedora-bootc-testcontainers.md)) is a small job.

## Python bindings and extension recipes

The [hello world](https://mini-swe-agent.com/latest/usage/python_bindings/):

```python
from minisweagent.agents.default import DefaultAgent
from minisweagent.models import get_model
from minisweagent.environments.local import LocalEnvironment

model = get_model(input_model_name="anthropic/claude-sonnet-4-5-20250929")
agent = DefaultAgent(model, LocalEnvironment())
agent.run("Write a hello world program")
```

The [cookbook](https://mini-swe-agent.com/latest/advanced/cookbook/) frames every custom agent as four choices: **agent class** (control flow: `DefaultAgent`, `InteractiveAgent` for human-in-the-loop), **environment class**, **model class** (`LitellmModel`, or `get_model` for auto-selection), and a **run script** that wires them (settable as the default entry point via `MSWEA_DEFAULT_RUN`). Two override hooks cover most customization:

- **`Agent.execute_actions(message)`**: intercept parsed actions (`message["extra"]["actions"]`), handle custom pseudo-commands (e.g. a `python_function` prefix parsed with `shlex`), delegate the rest to `super()`.
- **`Environment.execute(action, cwd)`**: handle or veto commands at the execution boundary; return an error dict (`{"output": ..., "returncode": 1}`) instead of raising.

Documented patterns: custom completion (raise `Submitted` with an exit message), and **action validation** — a config subclass with `forbidden_patterns`, raising `FormatError` in the agent or returning an error observation in the environment. A linked blog post covers parallel runs at scale with Ray.

## Local models

From the [local models page](https://mini-swe-agent.com/latest/models/local_models/): everything goes through litellm, so a local server is just `model_kwargs` with `custom_llm_provider`/`api_base`. The vLLM example:

```yaml
model:
  model_name: "hosted_vllm/ricdomolm/mini-coder-1.7b"
  model_kwargs:
    api_base: "http://localhost:8000/v1"
```

Local models usually lack pricing data, which makes litellm's cost tracking error. Options: `cost_tracking: "ignore_errors"` per model, the global `MSWEA_COST_TRACKING` variable, or (recommended) a litellm model-registry JSON loaded via `LITELLM_MODEL_REGISTRY_PATH`. Caveats: model names are case-sensitive, the provider prefix must match the registry's `litellm_provider`, and some errors (auth, context-window-exceeded, unsupported params) abort without retries. Ollama/llama.cpp/LM Studio are not documented explicitly but follow the same OpenAI-compatible pattern.

## Output files

From the [output files page](https://mini-swe-agent.com/latest/usage/output_files/): each run writes a `.traj.json` with `info` (model cost and call stats, full config including the classes used, `exit_status` such as `Submitted` or `LimitsExceeded`, and the final `submission` patch), `messages` (full history in OpenAI chat format plus an `extra` field carrying parsed actions, per-call cost, return codes, timestamps), and a `trajectory_format` version. Batch runs also write a SWE-bench-compatible `preds.json` keyed by `instance_id` with `model_patch` diffs. The bundled [inspector](https://mini-swe-agent.com/latest/usage/inspector/) browses trajectories interactively. The format changed at v2.0; v1 material and files don't match.

## Limitations (when not to use it)

Per the [FAQ](https://mini-swe-agent.com/latest/faq/): bash is the only tool; actions are parsed from fenced blocks (format errors are a real failure mode, bounded by `max_consecutive_format_errors`); no state persists between actions. The maintainers argue these rarely matter given benchmark scores, and point users who need custom tool interfaces, history processors, or richer YAML-driven behavior to full [SWE-agent](https://mini-swe-agent.com/latest/faq/). Note the `mini` CLI default is `LocalEnvironment` with no isolation — anything untrusted belongs in Docker or another sandbox.

## Options for the workshop

| Goal | Approach | Notes |
| --- | --- | --- |
| Try it on real tasks | `pipx install mini-swe-agent`, `mini-extra config setup`, run `mini` in confirm mode | Review every command; trajectories saved automatically. |
| Build our own coding agent on it | Python bindings: subclass `DefaultAgent`/environment hooks, own run script | ~4 small classes; action validation via `forbidden_patterns` pattern. |
| Sandboxed agent runs | `DockerEnvironment`, or a custom environment wrapping our Testcontainers setup | `execute()` is one method; aligns with [mini-agent-sandbox](../mini-agent-sandbox.rst) work. |
| Local-model experiments | vLLM/OpenAI-compatible server + litellm registry JSON | Fits our [local models](../local-models.rst) interest; set cost-tracking handling explicitly. |
| Evaluation / fine-tuning data | Batch runs; `.traj.json` linear histories | Trajectory = prompt, so transcripts are training-ready. |

## Suggested next experiment

Install the CLI, run one confirmed interactive task against this repo, and read the resulting `.traj.json` in the inspector to see the message/action format. Then write a ~50-line run script using the Python bindings with a `DockerEnvironment` and a `forbidden_patterns` validation subclass, and point it at a toy task. That exercises the three things we'd rely on — bindings, sandboxing, trajectories — before committing to it as a scaffold.
