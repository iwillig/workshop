# Configuration review fixes

## Goal

Make `workshop config validate` catch the reviewed configuration errors before an agent starts, and make the `--image` override behave predictably with the checked-in `workshop.yaml`. Preserve existing behavior for valid configurations and explicitly unlimited limits.

## Plan

1. **Validate execution limits.** Reject negative values for built-in agents' `step_limit`, `cost_limit`, and `wall_time_limit_seconds`; preserve zero as the documented unlimited value. Check CLI overrides as well as YAML so a negative `--step-limit` cannot bypass validation. Add tests for negative, zero, and positive values.
2. **Validate MCP server names early.** Share the server-name rule with `MCPToolAdapter` so validation and runtime cannot drift. Reject non-string names, invalid characters, empty names, and names containing `__` before starting any MCP server. Test valid and invalid names through `config validate` and the adapter.
3. **Validate tools against built-in environments.** Reject `read` and `edit` for Docker agents during configuration validation, matching the tools actually exposed by `BuiltinTools`. Preserve GitHub tools and custom environment extensibility; avoid assuming that a custom environment has the capabilities of a built-in one. Add local and Docker validation tests and a construction regression test.
4. **Handle `--image` overrides explicitly.** When switching a local agent to Docker, use `/` as the container working directory unless the user supplies `--cwd`; do not silently carry a host-local `cwd` into the container. If the selected tool set is incompatible with Docker, stop with an actionable CLI error rather than silently dropping tools or granting additional capabilities. Document that the default reviewer uses `read` and requires a Docker-compatible agent configuration to use `--image`. Test the checked-in reviewer's override, explicit `--cwd`, and a compatible Docker agent without launching Docker.
5. **Update documentation.** Describe limit semantics, MCP naming, Docker tool availability, and `--image` override behavior in the relevant configuration and agent guides. Keep the example `workshop.yaml` aligned with the actual behavior.

## Verification

- Run focused configuration, named-agent, native-tool, and CLI tests, including new regression cases.
- Run the complete test suite and Ruff; report any environment-dependent failures or skipped integration tests separately.
- Run `workshop config validate` against the checked-in configuration and verify invalid examples fail with actionable errors.
- No live model, MCP server, or Docker access should be required for the new regression tests.
