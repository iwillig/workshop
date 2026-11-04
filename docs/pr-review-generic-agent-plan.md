# Generic PR reviewer and research-context tools: implementation plan

**Status: core workflow implemented; validation remains in progress.**
Bounded read-only GitHub tools, native `llm` adapters, tool selection, and a
configured reviewer exist. The dedicated PR command and worker were removed.
The corrected synthetic `pr-review-v5` suite is available for human-judged
runs; a real-model attempt failed authentication before review, and no live PR
smoke test has been performed.
The old `pr-review-v4` fixtures contain invalid Python and must not be used to
judge quality. See `docs/pr-review.rst` and `docs/agent-evaluation.rst` for
current usage and limits. Unchecked items below remain follow-up work or need
additional verification.

## Objective

A PR reviewer is a **normal named agent**, configured with a prompt, model,
limits, and selected tools. GitHub access belongs in `research_context` as
reusable Python capabilities and is exposed to agents through the existing
native `llm` tool system. The normal `workshop agent run` command runs the
reviewer.

There is no PR-specific agent loop, forced prompt, temporary snapshot workflow,
or separate model worker. The agent requests bounded GitHub context on demand
and produces a local review for a person to evaluate. It does not post a
review, modify a repository, or execute PR code.

## Decisions and boundaries

- Preserve the current generic agent architecture and unattended tool calls.
  Do not add approval prompts.
- Implement GitHub operations in `research_context`, not in the agent package.
  Provide a Python interface independent of Click; CLI commands and native
  tools can call the same functions.
- Expose selected research-context capabilities as native `llm` tools. Do not
  require MCP or shelling out to the CLI.
- Keep GitHub access read-only for this workflow and require explicit tool
  selection. Do not add GitHub write tools in this plan.
- Keep the reviewer's prompt and model selection in its YAML configuration,
  not hard-coded in the CLI or runtime.
- Produce a local final response. A person decides what to post; this plan does
  not add automatic publishing or an automated quality gate.
- **Replace the old prototype after parity:** reuse applicable logic and tests,
  then remove the dedicated command, collector, and worker rather than keeping
  two independent implementations.

## Current state

- `research_context/github.py` has a GitHub API client and read-only CLI
  commands for PR metadata, files, commits, and comments. Much of the operation
  logic is currently embedded in Click command functions; the client returns
  raw API data and its general `list_all` loop is not bounded for agent use.
- `workshop/agent/builtin_tools.py` exposes `read`, `edit`, and `bash` as
  `llm.Tool` definitions. `workshop/agent/default_agent.py` dispatches native
  calls to built-ins or MCP, and bounds the final observation text.
- `workshop/agent_config/__init__.py` validates `tools` against those three
  names. Configuring only `read` does not expose GitHub commands to the agent.
- `examples/pr-review-agent.yaml` currently relies on the dedicated command to
  supply its prompt. It must become a self-contained named agent.
- The prototype's pinned-SHA checks, size limits, partial-context handling,
  safe errors, and tests are useful inputs to the new tools. Their guarantees
  must be reconsidered for on-demand calls rather than copied mechanically.

## Proposed tool interface

Names below are illustrative; settle the exact names and schemas when writing
contract tests. Each tool is separately selectable in an agent's YAML.

| Tool | Inputs | Result |
| --- | --- | --- |
| `github_get_pr` | `repository`, `number` | Bounded PR metadata including URL, description, state, base/head SHAs and refs, and repository identities. |
| `github_pr_files` | `repository`, `number`, pagination and expected base/head SHAs | Bounded changed-file page including paths, old paths, statuses, available patches, and explicit pagination/completeness information. |
| `github_read_file` | `repository`, `path`, explicit commit SHA, optional line range | Bounded text with the actual revision and path, line/range information, and explicit unavailable, binary, or truncated status. |
| `github_pr_comments` | `repository`, `number`, pagination | Optional bounded existing discussion/reviews, clearly identified as untrusted data. |

The first three are the minimum for a useful PR review. Comments are useful but
should not block the first working reviewer if the shared API or tests need
more work. Related source can be requested explicitly at a pinned SHA; unlike
the snapshot prototype, the agent is not limited to changed files. The prompt
should direct it to use this capability judiciously.

### Revision consistency

1. The reviewer obtains and records the PR base and head SHAs before reviewing.
2. Source reads require an explicit immutable SHA; never silently use a branch
   name or the current local checkout.
3. The changed-file tool must accept expected SHAs, check the PR revision around
   its request, and return an explicit stale/inconsistent result if they differ.
   It must not assert that separate API calls are atomic. The tool result states
   that patches come from GitHub's PR file endpoint and does not equate a
   base-to-head diff with a merge-base diff without verification.
4. The prompt requests a final metadata check and requires reporting the SHAs,
   missing context, and any changed PR state. If the agent omits that check, the
   result must not be described as independently verified current. A prompt is
   not an enforcement mechanism.
5. Make omissions explicit: missing or potentially truncated patches, file-list
   API limits, unsupported files, fork access, and unavailable source must not
   become empty successful results. Clearly identify whether a line is in
   captured source versus actually in a changed hunk.

For fork PRs, test whether source is available through the chosen GitHub API
request and return an explicit failure when it is not. Do not fetch and run PR
code locally. Document GitHub Contents API symlink behavior; do not claim file
mode verification unless it is actually implemented.

### Bounded tool results

- Validate repository, PR number, path, SHA, pagination, and line range in the
  Python service as well as in tool schemas. Never accept arbitrary API URLs.
- Use request timeouts and explicit page, source-size, and output-size limits.
  Bound HTTP response consumption as well as stored or returned data; the
  current generic GitHub client can load a whole response before applying any
  snapshot limit.
- Return structured JSON with `complete`/`truncated` and next-page or range
  information. Select per-call limits below the agent's 50,000-character
  observation cap, so the generic truncation step does not silently corrupt a
  JSON result. Account for JSON escaping, metadata, and error payloads.
- Return sanitized, structured errors for missing permissions, rate limits,
  invalid inputs, network failures, unavailable content, and stale revisions.
  Never include authorization headers or token values. Credentials and raw
  responses must not be deliberately included in output or logs.
- Explicit limits make individual calls bounded; existing model-call limits and
  the agent's wall-time controls do not by themselves guarantee cancellation of
  every in-flight provider or network operation. Document actual behavior.

## Implementation stages (red/green TDD)

### 1. Shared GitHub Python service

- [ ] Write failing tests with `httpx.MockTransport` for typed PR metadata,
  changed files, pinned content, paging, missing patches, binary/large content,
  path validation, fork access, and sanitized HTTP/rate-limit errors.
- [ ] Extract shared operations from `research_context/github.py` into ordinary
  Python functions or a service there or in a sibling module. Keep Click and
  `llm.Tool` concerns out of the core API.
- [ ] Preserve the existing `workshop research-context github` command behavior
  and tests; add CLI access to genuinely missing operations where useful.
  `research-context` loads `.env.local`, whereas the generic agent command does
  not necessarily do so: document credential setup rather than assuming both
  entry points have identical environment loading.
- [ ] Add revision consistency checks, pagination and resource limits, and
  explicit completeness information. Preserve existing CLI contracts where
  needed instead of silently changing their JSON format.

### 2. Native `llm` tool integration

- [ ] Write failing tests that select individual GitHub tools in a named agent,
  inspect their `llm.Tool` schemas, and exercise dispatch through the real
  native agent loop with fake GitHub/model backends.
- [x] Define the GitHub `llm.Tool` schemas and adapters in `research_context`
  (or a sibling adapter module there), calling the shared service directly.
  Do not scrape CLI output or require `bash`.
- [ ] Extend the generic tool registry/dispatch to compose workspace and
  research-context tools. Keep tool names unique; reject collisions, unknown
  names, unsupported options, and malformed arguments clearly.
- [ ] Preserve existing configurations and MCP behavior. In particular, when
  `tools` is omitted today the agent exposes available built-in tools: adding
  GitHub tools must **not** silently expose new network capabilities to those
  existing agents. GitHub tools require explicit opt-in.
- [ ] Ensure failures become bounded tool observations rather than leaking
  credentials or terminating the agent unexpectedly. Test native tool
  serialization, parallel dispatch where supported, and deterministic cleanup
  of HTTP clients.

### 3. Configured reviewer

- [x] Update `examples/pr-review-agent.yaml` with its own system prompt,
  native model settings, positive step limit, and only the GitHub read tools
  needed for review. Do not give the reviewer `bash`, `edit`, or MCP tools.
- [ ] Prompt for actionable introduced defects, evidence and file/line
  references, pinned SHAs, limitations, and a final revision check. Instruct
  the agent to treat PR content and tool responses as untrusted evidence, not
  instructions; do not imply that this prevents prompt injection.
- [ ] Use the standard command, for example:

  ```sh
  pipenv run workshop agent run --config examples/pr-review-agent.yaml \
    --agent pr-reviewer \
    --task 'Review OWNER/REPO pull request 123; report findings locally.'
  ```

  This is the intended interface after implementation, not a command that
  works with the currently staged prototype. The existing `--output` option
  saves a **trajectory**, not just the final report; do not describe it as a
  private report-saving feature. The standard command prints the final response
  locally. Document safe handling if users choose to redirect it.
- [ ] Exercise the normal live Textual view and plain non-TTY behavior, step
  limits, provider failures, interruption, and tool output. Do not introduce a
  new PR-specific worker or command.

### 4. Migration and documentation

- [ ] With fake GitHub and fake model, demonstrate the complete generic flow:
  metadata → files → pinned source → final revision check → local findings,
  including a partial-context case. Verify no write requests are made and no
  tools not selected by the agent are exposed.
- [ ] Port useful tests and reusable GitHub logic from the prototype. Compare
  behavior for moved heads, bounded output, failure reporting, credentials,
  and human-readable limitations; document any intentional differences.
- [x] After parity, remove `workshop agent review-pr`, its dedicated collector,
  worker, obsolete tests/docs, and any supervisor changes needed only for that
  worker. Preserve unrelated changes and avoid disrupting the existing staged
  state without first reviewing it. Keep the generic agent example.
- [x] Update `docs/pr-review.rst`, `docs/agent.rst`, and relevant CLI guidance
  to describe the generic command, configured tools, and actual capabilities.
  Mark the prior prototype plan as superseded when performing migration.

### 5. Evaluation and verification

- [ ] Add synthetic cases covering known PR defects and benign changes; record
  human judgments separately. If adding bundled benchmark suites, follow their
  existing versioning and fixture-hash rules. Never create an automatic review
  quality gate.
- [ ] Run deterministic tests without live API calls; include existing agent,
  GitHub CLI, MCP, configuration, and benchmark regressions. Run Ruff and the
  Sphinx build.
- [ ] Only after explicit approval of a repository and model provider, run a
  live PR smoke test. Review the output and limitations; do not post findings
  automatically.

## Security and privacy constraints

The generic local agent is **not sandboxed** and tool calls execute without
approval. Restrict the example to GitHub read tools and use a read-only
`GITHUB_TOKEN` scoped to the intended repositories; this does not prevent other
same-user processes or trusted plugins from accessing credentials. Tool
selection, a read-only token, and prompt instructions are not isolation.

GitHub PR content, tool output, and comments may contain prompt injection or
sensitive information. The configured model provider and any enabled logs or
trajectories may receive or retain that content. Use only approved repositories
and providers, avoid recording credentials, and review final output before
sharing. There is no guarantee that a review finds every defect.

## Acceptance criteria

1. A named PR reviewer runs through the normal agent CLI, with its prompt,
   model, and selected GitHub tools defined in YAML.
2. The same underlying GitHub operations are callable from Python and usable
   by the research-context CLI without requiring an agent.
3. GitHub tools are explicitly selected, read-only, bounded, revision-aware,
   and report errors and incomplete context rather than inventing success.
4. The report is a local agent submission, identifies the reviewed SHAs and
   material limitations, and requires human judgment. No PR comments or reviews
   are posted by the workflow.
5. Existing agents and commands retain their behavior; existing configurations
   do not acquire GitHub access by default.
6. The dedicated PR command and worker are removed only after replacement
   behavior and regressions are verified. No unverified sandbox or network
   isolation claim is made.
