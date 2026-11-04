# Trace review with a local model: proposed design

**Status: trusted-development prototype; local-only boundary unverified.**
The user chose a simpler development workflow using synthetic or non-sensitive
traces, not an isolation claim. Some records and CLI commands exist, but this
proposal previously overstated the protection provided by a proxy and loopback
configuration. Those measures do not isolate network access. Do not use
sensitive traces until a boundary is redesigned and independently verified.

## Goal

Review stored benchmark trajectories with a locally controlled model and turn
that review into evidence-linked, human-judged improvement proposals. The
reviewer observes how an agent worked; it never scores, promotes, or applies
anything by itself.

Trace review is the first step of the learning loop: run → capture trace →
review → propose → human decision → (separately) promote and re-benchmark.

## Decisions

- **Local runtime:** a small GGUF model served by `llama-server` on
  `127.0.0.1`, registered in `llm` as an OpenAI-compatible model with an
  explicit model ID. The reviewer never uses the llm default model; the model
  must be named explicitly. The specific model file is an open decision.
- **Local-only boundary:** an unmet requirement, not an established property.
  The prototype checks the registered model's base hostname, rejects configured
  tools and MCP servers, and sets proxy variables during the query. Those
  checks cannot prevent a plugin, client, redirect, or loopback service from
  forwarding data elsewhere; proxy settings may be ignored. Model validation
  and model construction are separate, and host process networking is not
  isolated. An opt-in HTTP canary and local request can test those particular
  paths, not prove a general boundary. The real-server probe has not been run.
- **Trace content is untrusted.** Traces may contain prompt-injection text.
  Reviewer instructions must treat trace content as data to observe, never as
  instructions to follow. The reviewer output is a record, not an action.
- **Output is proposals only.** The reviewer produces structured observations
  and candidate proposals. Nothing is applied to prompts, suites, or skills by
  this workflow.

## Data contracts

All records are versioned, private JSON in the same explicit storage root as
benchmark reports. Pydantic models with `extra="forbid"`, `schema_version: 1`.

- **TraceReview:** ID, run ID, trace storage key and SHA-256 (must match the
  run's trace reference), reviewer model identity and prompt version, bounded
  observations (list of short text findings with optional evidence quotes),
  created timestamp, and status (`completed` or `failed`).
- **Proposal:** ID, source review ID, kind (`eval-case`, `prompt-change`, or
  `skill-note`), a bounded rationale, evidence references (review ID plus
  observation indexes; never raw trace copies), and the candidate payload as
  descriptive data. Status starts at `proposed`.
- **ProposalDecision:** ID, proposal ID, decision (`accept`, `reject`, or
  `revise`), reviewer name, rationale, timestamp. Decisions are append-only
  history; the latest decision per proposal is reported, like case reviews.
  Acceptance never applies anything; promotion to a versioned suite is a
  separate, later, user-directed action outside this design.

The prototype truncates serialized trace text and records that truncation.
It retains portions of the overall head and tail, but can omit a case's final
submission; preserving all submissions within a strict budget remains open.

## CLI sketch

Exact names are subject to implementation:

```text
workshop eval review-trace RUN_ID --config reviewer.yaml --agent reviewer \
  --storage /private/benchmarks
workshop eval inspect REVIEW_ID --storage /private/benchmarks
workshop eval propose REVIEW_ID --kind prompt-change --storage ...
workshop eval decide PROPOSAL_ID --decision reject --reviewer NAME \
  --rationale "..." --storage /private/benchmarks
workshop eval proposals --storage /private/benchmarks
```

`review-trace` performs configuration and trace-hash checks, but they do not
establish a local-only boundary or authenticate records against an actor able
to modify both the trace and report.

## Verification

Red/green for every slice. Deterministic tests use a fake local model; mocks
never count as evidence of the network boundary.

1. Records and storage: validation, private permissions, linked hashes.
2. Reviewer runner: configuration validation (loopback URL, explicit model,
   no tools, no MCP), bounded truncation, untrusted-content handling in the
   prompt contract, and failure classification.
3. Opt-in diagnostic (requires `llama-server` and a model file): test the
   selected HTTP client's proxy behavior and a loopback review. Do not treat a
   successful canary as proof of a network boundary.
4. Proposals and decisions: linkage, append-only history, no automatic
   application of anything.
5. Documentation with the trust limits stated above.

## Open decisions

- Whether and when to pursue an independently verified local-only boundary;
  the current trusted-development prototype does not provide one.
- Which GGUF model and context size; how much of a trace fits in the budget.
- Whether observations should be free text or a fixed small schema first.
- Retention and deletion for traces and reviews (they are sensitive).
- How to design and independently verify routing that truly keeps traces local,
  including model plugin behavior, redirects, DNS, and proxy bypass.
- How to ensure truncation retains necessary case evidence and submissions.
