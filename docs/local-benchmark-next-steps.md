# Local benchmark validation and expansion plan

**Status:** The local benchmark implementation and both live smoke runs are
complete. The `hf-glm` review run identified the expected defect and received
a separate human pass decision. A later `hf-glm` coding run passed the
deterministic check. The v2 suites and private review records are implemented.

## Scope and safety

Continue with trusted development fixtures and report-only results. Local
execution is **not a security boundary**: agents and coding checks run with the
developer's permissions and can access local files, credentials, networks, and
configured MCP servers. Remote providers may receive fixture content. Use an
explicit owner-only private directory for results; records are not automatically
redacted.

This plan does not add isolation, CI quality gates, automatic review judgments,
or automatic prompt changes. The stronger sandbox remains separate work.

## 1. Run the review smoke test

- [x] Run `review-v1` through the CLI using `examples/review-agent.yaml` and an
  explicit private storage directory. Earlier attempts returned HTTP 401 and
  were recorded as infrastructure errors; a later run succeeded.
- [x] Inspect the saved report and confirm the outcome is pending human review.
- [x] Compare the agent's finding with the expected empty-input defect.
- [x] Rerun after provider authentication was corrected. The successful run
  used `hf-glm`; earlier 401s were infrastructure errors, not review failures.

The configured `hf-glm` model may send fixture content to a Hugging Face
provider. Running this test can incur provider costs and executes the configured
agent locally.

## 2. Add a coding-agent smoke test

- [x] Add an opt-in live coding test parallel to
  `tests/test_local_benchmark_live.py`.
- [x] Require an explicitly selected named coding agent and configuration; do
  not silently select a provider.
- [x] Run the coding fixture with a temporary named `hf-glm` coding agent and
  verify that its private report records a pass from the deterministic check.
- [x] Add fake-agent coverage for both passing and failing coding results.
- [x] Keep the live benchmark and model tests out of the default test run;
  each requires explicit opt-in.

A model's incorrect solution is a benchmark failure, not automatically a runner
failure. Live execution must be explicitly enabled and can incur provider costs.

## 3. Expand the suites

- [x] Generalize fixture loading and copying to support multiple files rather
  than requiring `calculator.py`.
- [x] Preserve `coding-v1` and `review-v1` definitions so existing reports
  remain identifiable.
- [x] Add versioned v2 suites, initially targeting three small coding cases and
  three small review cases with distinct failure modes.
- [x] Pin fixture and scoring hashes and reject missing or modified inputs.
- [x] Test multi-file copying, hash mismatches, versioning, per-case cleanup,
  and independent outcomes within a multi-case suite.

Keep each case small enough for a person to understand and maintain. Fixture
copies and separate check files do not prevent a local agent from accessing
other same-user files.

## 4. Record human review decisions

- [x] Define a private review record linked to the exact run, case version, and
  suite hash.
- [x] Record a decision of pass, fail, or inconclusive, along with reviewer
  name, timestamp, and a short rationale for missed defects or false positives.
- [x] Provide a command to record a decision and show it alongside the original
  findings in a report.
- [x] Preserve the original pending-human-review result; store human judgment
  separately and make subsequent decision changes attributable.
- [x] Test invalid decisions, correct run and case links, private storage,
  report display, and preservation of the original result.
- [x] Verify that pending and inconclusive cases are not counted as passes.

A live review judgment was recorded separately from the original pending
result. Human decisions are report data, not automatic judgments or CI gates.

## Delivery and verification

- [x] Complete the review smoke test; earlier authentication failures are
  distinguished from review failures.
- [x] Add coding smoke-test support and fake-agent coverage.
- [x] Add multi-file fixture support and expanded suites.
- [x] Add human-decision records and report display.
- [x] Update usage and safety documentation.
- [x] Run Ruff, the applicable test suite, and the documentation build. The
  deterministic suite passed with the separate live model test and
  environment-specific test excluded; opt-in diagnostics were skipped.

Use red/green TDD for implementation slices. Run live tests only when explicitly
enabled and document which provider and agent were used.
