# Local benchmark validation and expansion plan

**Status:** Implementation is in progress. The review CLI smoke test reached
`hf-glm` but received HTTP 401, so successful live review remains blocked on
provider authentication. The v2 suites and private review records have been
implemented; see the checklist for verification status.

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
  explicit private storage directory. The provider returned HTTP 401; the
  runner saved an infrastructure-error result.
- [ ] Inspect the saved report and confirm the outcome is pending human review.
- [ ] Compare the agent's finding with the expected empty-input defect.
- [ ] Resolve provider authentication and rerun. Treat this infrastructure
  error separately from a model's failure to find the defect.

The configured `hf-glm` model may send fixture content to a Hugging Face
provider. Running this test can incur provider costs and executes the configured
agent locally.

## 2. Add a coding-agent smoke test

- [x] Add an opt-in live coding test parallel to
  `tests/test_local_benchmark_live.py`.
- [x] Require an explicitly selected named coding agent and configuration; do
  not silently select a provider.
- [ ] Run the coding fixture and verify that the report is stored and the
  outcome reflects the deterministic check.
- [x] Add fake-agent coverage for both passing and failing coding results.
- [x] Keep live model tests out of the default test run.

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

Human decisions are report data, not automatic judgments or CI gates.

## Delivery and verification

- [ ] Complete the review smoke test and address integration failures.
- [x] Add coding smoke-test support and fake-agent coverage.
- [x] Add multi-file fixture support and expanded suites.
- [x] Add human-decision records and report display.
- [x] Update usage and safety documentation.
- [x] Run Ruff, the applicable test suite, and the documentation build. The
  default suite passed; opt-in live and sandbox diagnostics were skipped.

Use red/green TDD for implementation slices. Run live tests only when explicitly
enabled and document which provider and agent were used.
