# Read-only GitHub PR review agent: implementation plan

**Status: superseded by ``docs/pr-review-generic-agent-plan.md`` and
implemented there.** This plan described a first PR-review workflow using a
dedicated host-side collector, temporary snapshot, and separate model worker.
The implemented approach instead uses a normal configured agent with bounded
read-only GitHub research tools exposed through the native ``llm`` tool
system.

## Goal

Given a repository and pull request number, gather a bounded snapshot of the PR,
run a named review agent, and produce a local report of actionable defects and
review limitations. A person decides whether to post any findings to GitHub.

## Agreed scope

- **Local report only:** do not post reviews, comments, reactions, or status
  changes to GitHub. The existing unattended tool-call behavior is unchanged.
- **Prepared snapshot:** trusted host-side code gathers PR context before the
  agent runs. The agent reads that snapshot rather than receiving GitHub tools.
  Preventing accidental GitHub-token inheritance requires explicit work; the
  current local environment inherits host environment variables.
- **Pinned revisions:** record the PR's base and head SHAs, identify the diff's
  comparison semantics, and label all fetched source with its actual revision.
- **Report incompleteness:** missing or truncated patches, source, comments, or
  API results are visible to both the agent and the report reader. They are
  never silently treated as a clean review.
- **Human judgment:** findings are proposed observations, not an automatic
  GitHub review or a quality gate.

## Trust and privacy

The local agent is **not sandboxed**. Limit its configured built-in tools to
`read` and do not configure MCP servers or shell tools for the first version.
This reduces available actions but is not a security boundary. Use a temporary
workspace containing only the prepared snapshot, not the live checkout, and
use trusted agent configuration.

PR descriptions, comments, file paths, patches, and source are **untrusted
data**. They may contain instructions aimed at the model. The prompt must tell
the reviewer to treat them as evidence, not instructions; prompt text alone
cannot guarantee resistance to injection. No PR code or test command is run.

A configured remote model may receive any snapshot content it reads. Restrict
use to repositories and providers approved for that data. Private reports and
optional trajectories may contain sensitive content; they are not automatically
redacted or encrypted. Do not put tokens in snapshots, prompts, reports, or
logs deliberately. Temporary-file deletion is best effort and does not assure
secure erasure.

## GitHub information required

### Minimum

1. Repository identity, PR number, URL, title, description, state, and draft
   status where available.
2. Base and head repository/ref/SHA, including whether the head is from a fork.
3. The changed-file list: paths, previous paths for renames, status, additions,
   deletions, and patches where GitHub provides them.
4. Source at the **pinned head SHA** for supported changed text files and at
   the appropriate pinned base revision when needed to understand deletions or
   previous behavior. Label every source file with its revision and path.
5. Explicit completeness status for pagination, missing patches, unsupported
   or oversized files, fetch failures, and truncation.

GitHub's PR-file API has documented limits and may omit patches. Do not infer
that an absent patch is an empty change. Avoid claiming that base SHA versus
head SHA is identical to GitHub's displayed PR diff without verifying the
comparison/merge-base semantics. Record the source of the diff and any
unresolved comparison limitation.

### Optional, bounded context

- PR discussion, review comments, and previous review summaries to reduce
  duplicates; distinguish resolved or outdated context where the API provides
  that information.
- Commit messages and relevant tests or project instructions when they can be
  retrieved at a known revision within the snapshot limits.
- CI status can be added later; do not imply that checks passed when status was
  not collected.

A `GITHUB_TOKEN` with the appropriate read access is needed for private
repositories and authenticated limits. Public repositories may be readable
without one. The first version must not require GitHub write permissions.

## Design sketch

### 1. Host-side PR context collector

- Refactor or reuse the HTTP and pagination logic in `research_context.github`
  without coupling the agent loop to Click output. Keep existing commands and
  their JSON behavior compatible.
- Accept an explicit `OWNER/REPO` and positive PR number. Read PR metadata,
  changed files, and optional discussion through GitHub's API.
- Capture base and head identifiers before collecting data; fetch file contents
  by explicit commit SHA, never by a moving branch name. Read PR metadata again
  after collection. If either relevant SHA changed, mark the snapshot stale
  and do not present it as a consistent review; fail or require a fresh run.
- Record API pages fetched, source revision, content hashes where practical,
  and missing/truncated content. Enforce explicit per-file, total-byte, file
  count, API-page, and request-time budgets. Choose conservative documented
  defaults during implementation; hitting a budget creates an explicit
  incomplete result, not a hidden truncation.
- Treat API file paths as untrusted: validate relative paths and reject
  traversal, absolute paths, links, special files, and collisions before
  materializing anything. Never extract a PR archive into the live checkout.
- Represent deleted, renamed, binary, unavailable, and oversized files
  explicitly. A missing source file is not a successful fetch.

### 2. Snapshot and review agent

- Create a fresh private temporary snapshot containing a manifest, the PR
  metadata, available patches, bounded source, and a completeness summary.
  The manifest identifies the pinned revisions and maps safe snapshot paths to
  original repository paths. Keep credentials and private output storage out of
  the snapshot.
- Define and test how the GitHub token is withheld from the agent's environment
  and model configuration, while allowing explicitly needed model credentials.
  The current local runtime inherits the host environment, so a prepared
  snapshot alone does not accomplish this. Even with filtered environment
  variables, a same-user process may be able to access host credentials; this
  is data minimization, not an isolation guarantee.
- Supply the agent with the manifest path and review task; use a dedicated
  named YAML agent configured for native tool calls with only `read` enabled.
  Do not give it `bash`, `edit`, GitHub write tools, or MCP servers.
- Run with explicit step and command limits using the existing foreground agent
  path. Detect agent/model errors and interruption; clean up the snapshot on
  normal completion and handled failures. A hard stop can leave artifacts or
  remote model work behind.
- Do not assume `read` restrictions, a prompt, or a temporary directory
  protects the host against a hostile model or process. Restrict the workflow
  to trusted configurations and repositories under the current local model.

### 3. Local report

Define and validate a versioned report before implementing the command. It
should contain:

- Repository, PR number and URL, base/head SHAs, diff provenance, time, and
  agent/model identity where available.
- Findings with severity, repository path, line or range when supported,
  concise explanation, impact, and evidence. Validate paths and ranges against
  the captured snapshot; explicitly mark locations that cannot be verified.
- A separate limitations section listing unavailable/truncated content,
  unsupported files, stale PR state, and checks not performed.
- Run status that distinguishes completed review, incomplete context, model or
  provider failure, and interrupted execution. `no findings` must not conceal
  incomplete context or infrastructure failure.

Save only to an explicitly selected private location when persistence is
requested; otherwise show the report locally. Do not invent token or cost
figures. Existing optional trajectory/logging settings have separate privacy
risks. A malformed model response must be visible as an error, not converted
into an empty successful review.

### 4. Public interface

The exact name and arguments are a design sketch, not an existing command:

```text
workshop agent review-pr OWNER/REPO PR_NUMBER --config agents.yaml \
  --agent pr-reviewer [--output /private/review.json]
```

Print progress and the local report; never publish to GitHub. Explicitly warn
about local execution, remote model disclosure, and incomplete or stale context.
Define exit statuses for setup/infrastructure failure separately from findings;
findings do not become a CI gate. Recheck the pinned PR head before presenting
or consuming results and label a changed PR as stale.

## Red/green delivery plan

- [ ] **Contracts and fixtures:** write failing tests for versioned snapshot and
  report models, invalid paths, missing context, status distinctions, and
  malformed model output; implement the smallest passing contracts.
- [ ] **Collector:** add mocked GitHub API tests for pagination, HTTP errors,
  permission failures, absent/truncated patches, binaries, renamed/deleted
  files, large inputs, path collisions, and forked PRs. Verify source is fetched
  by SHA and moving base/head is detected. Reuse the current GitHub client.
- [ ] **Snapshot lifecycle:** test safe path mapping, byte/file/page budgets,
  manifest provenance, temporary-directory permissions, cleanup, credential
  environment filtering, and no token deliberately persisted. Tests must use
  synthetic data and fake clients.
- [ ] **Reviewer adapter:** test a fake model and executor against a prepared
  snapshot, including prompt-injection text, missing files, non-submission,
  timeout, interruption, and provider failure. No live GitHub or model call in
  the default test suite.
- [ ] **Report and CLI:** test valid findings, unverifiable paths/lines,
  incomplete snapshots, invalid responses, explicit local output or private
  persistence, and nonzero infrastructure errors. Confirm no GitHub write
  request can be made through the implemented workflow.
- [ ] **Evaluation:** add small versioned synthetic PR fixtures with known
  defects and benign changes. Keep review outcomes pending human judgment;
  test findings and false positives with a person, not an automatic LLM judge.
- [ ] **Opt-in smoke test:** with explicit repository/provider permission, run
  against one designated PR and a trusted configuration. Record what was
  available, inspect the local report, and do not post it automatically.
- [ ] **Docs and verification:** document permissions, example usage, trust
  boundaries, provider data exposure, limits, cleanup, and troubleshooting.
  Run Ruff, focused and broad deterministic tests, and the docs build.

## Open questions before implementation

- Which repositories and model providers are approved for real PR content?
- Which metadata and surrounding files must the first snapshot include by
  default, and what size and request budgets are appropriate?
- Does the initial report schema and its critical/high/medium/low severity
  scale meet the team's needs?
- The selected first-version policy is a clearly labelled partial report with
  exit zero; should that policy change after practical use?
- Where should reports be saved when requested, and what retention policy applies?

Resolve consequential choices with the user before implementation. Private
GitHub context and trace handling must not be presented as network-isolated.
