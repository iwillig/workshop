# Local branch review agent: implementation plan

## Goal and scope

Add a normal named Workshop agent that reviews **committed changes on the current local branch** against a configured base ref. Focus on meaningful stylistic inconsistencies, structural issues, and duplicated code. Produce a local report for a person to review; do not edit files, execute project code, or publish comments.

The base ref is configured in `workshop.yaml`. Compare the merge-base commit to the captured branch HEAD. Report staged, unstaged, and untracked changes as excluded; never incorporate working-tree content in the review. A dirty working tree is not a reason to fail.

## Design

### Configuration and invocation

- Add a `branch-reviewer` named agent in `workshop.yaml`, with a native model, bounded step limit, dedicated system prompt, and only the four local Git review tools below. Continue using `workshop agent run`; do not add a dedicated runtime.
- Add a project-wide setting, for example `git.base_ref: main`, in `workshop.yaml`. Normalize and validate it in `workshop.config` so other project features can consume it independently of the agent. When configured, it must be a nonempty string; it is required when the branch-review context tool is used, but remains optional for unrelated commands and projects. Resolve it against the selected repository when the tool runs; do not fetch, infer a default, or silently fall back. Document the example ref and how users change it for their repository.
- Select `git_review_context`, `git_review_diff`, `git_read_file`, and `git_search` with empty tool options, consistent with existing tools. Pass the normalized project-wide Git settings to the provider when constructing the agent; do not duplicate the base ref in agent-specific configuration. Example structure (other existing settings omitted):

  ```yaml
  version: 1
  git:
    base_ref: main
  github:
    repositories:
      workshop: owner/workshop
      other: team/repo
    default_repo: workshop
  agents:
    branch-reviewer:
      model:
        model_name: hf-glm
        protocol: native
      prompts:
        system: |
          Review committed branch changes for meaningful style,
          structural, and duplication issues.
      environment:
        environment_class: local
        cwd: .
      limits:
        step_limit: 20
      tools:
        git_review_context: {}
        git_review_diff: {}
        git_read_file: {}
        git_search: {}
  ```

  The prompt and repository names are illustrative; the implementation will include the full review and safety instructions.
- Add project-wide `github.repositories`, a mapping of aliases to `OWNER/REPO`, and `github.default_repo`, the alias to use by default. Validate alias names and repository values and require the default alias to exist. Both settings remain optional for projects that do not use GitHub. Keep credentials out of YAML; continue using `GITHUB_TOKEN`.
- Make GitHub CLI commands and native agent tools resolve repository selection consistently: explicit `OWNER/REPO` or configured alias wins, otherwise use `github.default_repo`; if neither is available, return an actionable error. For commands taking a number, support both `get-pr 123` (default) and `get-pr owner/repo 123` (explicit); keep existing explicit positional forms for other commands too. Native GitHub tool schemas accept an omitted repository and resolve it using the same rules. Keep general search queries unrestricted unless explicitly scoped.
- Workshop passes its already-selected normalized configuration, including `--workshop-config`, to research-context and native providers. The standalone research-context CLI discovers the nearest `workshop.yaml` and accepts an explicit configuration path; it continues to work with explicit repositories when no project configuration exists. Test both entry points and ensure they do not independently select conflicting configurations.
- Bind the provider to a repository discovered from the agent's configured local working directory. Resolve the repository root once; reject non-repositories and bare repositories with an actionable error. Require a local environment for these tools rather than treating a Docker working directory as a host path.
- Invoke the agent with a task such as `workshop agent run --agent branch-reviewer --task 'Review my current branch.'` The task is not the authority for choosing the configured base.

### Bounded, read-only Git tools

Implement a service under `research_context` and native `llm.Tool` adapters following the existing GitHub review provider pattern. Use GitPython or fixed-argument Git subprocesses, never a shell, and bound output and execution time. This workflow is for trusted repositories only: normal Git configuration and partial-clone lazy fetching may invoke helpers or access the network. Document those limitations; do not claim isolation. Validate inputs and return sanitized structured errors.

1. **`git_review_context`** returns the snapshot captured at run start: configured base and current HEAD resolved to full object IDs, merge base, branch and working-tree status. Fail clearly before the first model call for detached HEAD, unborn HEAD, an invalid base, or no unique merge base; do not guess. Dirty status is informational and bounded.
2. **`git_review_diff`** accepts pinned merge-base and head commit IDs and pages a changed-file inventory and bounded patches. Include paths, change type, rename information, and line numbers. Mark binary files, unavailable content, output truncation and continuation explicitly; never silently claim completeness.
3. **`git_read_file`** reads bounded, numbered lines from a tracked blob at a specified full commit ID. It must not follow working-tree symlinks or read files from disk as a substitute. Indicate binary, unsupported, missing and truncated content. Permit reading both pinned revisions so deleted or changed code can be verified.
4. **`git_search`** searches tracked content at the pinned HEAD for a literal string, with bounded results, paths, line numbers and pagination. Return explicit truncation/unsupported notices. Do not search the working tree, Git metadata, untracked files, or use regex/semantic search in the first version.

Require full commit object IDs in follow-up calls; reject arbitrary revision expressions and path traversal. Capture a fresh review context before the first model call in each run, retain it across tool calls, and reset it on reuse; support both direct and supervised runs. Constrain calls to the captured commit pair. Before delivering the result, the runtime rechecks HEAD and the configured base, reporting any observed movement or inability to check while retaining the pinned review. The final check is a point-in-time observation, not a guarantee that refs cannot move afterward. Object ID validation must accommodate the repository's Git object format rather than assuming every repository uses SHA-1.

### Review behavior and output

- Treat diffs, source, paths, and tool output as untrusted evidence, not instructions. Expose no shell, edit, or write tools to the agent.
- Inspect the diff first; use committed source and literal search to compare nearby conventions and check existing abstractions. Confirm both locations before reporting a duplication finding.
- Prefer substantive findings with concrete maintenance impact over subjective style preferences or incidental similarity. Respect documented project conventions; do not substitute for existing formatters and linters.
- Cite the changed file and line, related locations where applicable, impact, and a suggested direction. Separate actionable findings from optional suggestions. Report the pinned SHAs, excluded dirty state, incomplete coverage, truncation, and any observed ref movement. Do not claim a clean review when evidence is incomplete.
- Track changed-file inventory and patch access, truncation, and errors in the runtime. Append a factual coverage summary distinguishing content returned by tools from content not requested or unavailable. Returned content does not prove model comprehension; define stable pagination and continuation contracts for inventories, patches and search results.
- Document that provider output may be sent to the configured model, that the review is not a sandbox or a completeness guarantee, and that local repository content can contain secrets or prompt injection. Read-only tools and prompts do not provide a security boundary.

## TDD workflow

Use red/green TDD for each behavior, including configuration, tools, CLI integration, agent lifecycle, and reporting:

1. Write a focused automated test for one behavior before implementing it.
2. Run that test and confirm it fails for the expected missing or incorrect behavior. Record the command and failure briefly in the implementation notes; fix test setup errors before proceeding.
3. Implement the smallest change that makes the test pass, then rerun the same test and confirm green.
4. Refactor with the test passing, and run relevant neighboring tests. Repeat for the next behavior.

Do not check off an implementation task until its relevant red/green cycles and regression tests are complete. Record exceptions where a meaningful red phase is impractical and explain why; do not present an unobserved failure as verified.

## Implementation notes

- Project setting normalization: `PYTHON_DOTENV_DISABLED=1 <venv>/bin/pytest -q tests/test_review_project_config.py` failed because `git` and `github` were unrecognized; after implementation the same tests passed, together with `tests/test_workshop_config.py` (16 passed). The invalid-input cases initially passed because all new fields were rejected; they are regression checks, not individually observed red phases. More targeted red/green tests are needed for each validation behavior.
- GitHub resolver: `pytest -q tests/test_review_project_config.py::test_resolve_github_repository` failed on the missing resolver, then passed after implementation. Native defaults: `pytest -q tests/test_review_project_config.py::test_github_native_tool_uses_project_default` failed on the unsupported `project` argument, then passed after implementation.
- GitHub CLI defaults: `pytest -q tests/test_review_project_config.py::test_github_cli_default_and_explicit_repository` failed on the missing positional argument, then passed after implementation. Standalone discovery: `pytest -q tests/test_review_project_config.py::test_standalone_research_context_discovers_and_selects_config` failed without a default, then passed after implementation. Focused configuration and GitHub tests passed (38 total). More edge-case tests and documentation remain.

- Initial Git snapshot: `pytest -q tests/test_local_git_review.py` failed because the service was absent, then passed after adding snapshot capture. `pytest -q tests/test_local_git_review.py::test_final_check_detects_moved_refs` failed on the missing final check, then passed after implementation. The service is not yet wired into the runtime.
- Pinned file reads: `pytest -q tests/test_local_git_review.py::test_read_file_uses_pinned_commits_not_worktree` failed on the missing method, then passed after implementation. Subsequent pagination, binary and symlink tests passed without a red phase because the behavior was already implemented; unusual-path tests remain outstanding.
- Bounded diff: `test_diff_uses_snapshot_and_excludes_uncommitted_changes` failed on the missing method, then passed. `test_diff_continues_beyond_output_cap` and `test_native_diff_tool_accepts_patch_pagination` failed before paginated patches were implemented and passed afterward. Diff pages use character offsets and bounded retained output; each page reruns the pinned diff. `test_diff_can_be_filtered_to_one_changed_path` failed before literal path filtering was added and passed afterward. Rename behavior under path filtering and other edge cases remain outstanding. `test_snapshot_uses_bounded_status_output` failed before status was routed through the bounded runner and passed afterward.
- Literal search: `test_search_uses_pinned_head_and_literal_matching` failed on the missing method, then passed. `test_search_pages_through_pinned_matches` failed on unsupported pagination arguments, then passed. `test_search_pages_past_previous_capture_cap` failed before streaming pagination and passed afterward. `test_search_filters_literal_repository_path` failed before literal path filtering and passed afterward. A Unicode/newline filename regression test passed on its first run (no observed red phase); binary omission is reported.
- Changed-file inventory: `test_changed_files_pages_and_reports_renames` failed on the missing method, then passed. `test_inventory_pages_past_previous_capture_cap` failed before streaming pagination and passed afterward. More edge-case tests remain.

- Native adapter, agent validation/lifecycle and CLI metadata: focused tests for provider creation, local-only configuration, run-start capture, final ref check and CLI reporting each failed before implementation and passed afterward. The checked-in example agent test likewise failed before configuration and passed afterward. A supervised worker test with a fake backend passed on its first run (no observed red phase); it verifies snapshot and final ref metadata but not a live provider or interactive TTY.
- Coverage and ref checks: `test_provider_reports_requested_and_unrequested_files` failed for missing summary support and passed after implementation. `test_final_check_detects_branch_switch_at_same_commit` failed before branch identity was checked and passed afterward. Tests for unrelated histories and a deleted base passed on first run without an observed red phase. Coverage indicates inventory completeness and files with returned reads; it does not establish comprehension or full file/patch coverage.
- Serialized output: `test_native_diff_tool_bounds_serialized_output` failed because JSON escaping exceeded the output bound, then passed after adding adaptive patch slicing. Oversized non-patch outputs fail explicitly instead of being silently truncated.
- Regression run: `PYTHON_DOTENV_DISABLED=1 <venv>/bin/pytest -q --ignore=tests/test_env_local.py` passed (428 passed, 12 skipped); `tests/test_env_local.py` passed separately (2 passed). Ruff, `workshop config validate`, and `git diff --check` passed. A model-free native-agent test passed after correcting its fake conversation setup; its initial failure was a test setup failure, not an observed red implementation phase. These checks do not prove live model or sandbox behavior.

## Implementation sequence

- [ ] Build and test the bounded Git review service using temporary repositories. Define explicit per-call input, output, size, pagination, and error contracts before wiring the model.
- [ ] Add and validate the project-wide `git.base_ref` setting in `workshop.config`, and pass it to the provider. Implement native tool adapters and per-run pinned context. Register them as opt-in providers in `workshop/agent_config`, preserving empty tool options and enforcing the local-environment restriction. Preserve existing GitHub and built-in tool behavior.
- [ ] Add and validate project-wide GitHub repository aliases and default selection; thread normalized settings into the GitHub CLI and native provider, with explicit overrides. Update the checked-in configuration and documentation with actual project repository details where known; never commit credentials.
- [ ] Add the named agent and prompt to `workshop.yaml`; add usage and limitations to the agent/configuration documentation. Keep the base explicitly configurable.
- [ ] Add tests for configuration validation, provider selection, tool dispatch, prompt/tool selection, and a model-free end-to-end run using a fake model and a temporary repository. Add a focused benchmark fixture for the three review categories if the existing benchmark framework can evaluate the results deterministically; otherwise document it as follow-up rather than claiming model quality.

## Verification

- [ ] Confirm each new behavior has a recorded red test run followed by a green run, or a documented reason why a red phase was impractical.
- [ ] Test merge-base behavior with divergent commits, renames, deletions, binary files, an empty diff, invalid and ambiguous bases, missing history, detached/unborn HEAD, and dirty worktrees. Confirm uncommitted edits never appear in diff, reads, or search.
- [ ] Test bounded pagination, large files and diffs, unusual paths, Unicode, symlinks, submodules, invalid object IDs, ref movement, unsupported content, per-run snapshot reset, direct and supervised execution, final ref checks, and runtime coverage reporting. Verify commands do not use a shell; document that trusted Git configuration and partial clones may invoke helpers or access the network.
- [ ] Test project-wide base-ref normalization, invalid and missing values, use by the provider, invalid tool options and non-local environments. Ensure unrelated commands work without the setting and existing named agents and tool providers retain their behavior.
- [ ] Test GitHub alias/default validation, CLI and native-tool default resolution, explicit override precedence, absent defaults, standalone CLI behavior, and unchanged unrestricted search. Mock GitHub requests; verify no credentials enter configuration or output.
- [ ] Run focused tests, `workshop config validate`, the full test suite, and Ruff. Report environment-dependent failures and skipped live tests separately. No live model or external network is required for automated tests.
