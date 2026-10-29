# Component interfaces for the workshop

## Summary

A shared operation and data contract is a promising starting point for a workshop that runs on a person's machine or in the cloud. A CLI and an HTTP API can expose equivalent operations without requiring every local invocation to run through a server. Separately deployed services can use HTTP and JSON where remote access or independent deployment is useful. This is a recommendation for exploration, not an architectural decision.

The main trade-off is between one execution path and local simplicity: making the CLI an HTTP client exercises the same server path everywhere, but requires a reachable server even for local work. Direct local execution avoids that requirement, but needs contract tests to keep local and remote behavior aligned.

## Options

| Approach | Local use | Remote use | Costs and risks |
| --- | --- | --- | --- |
| CLI calls an HTTP service | Requires a running local service, or a way to start one. | CLI can call a remote service. | One transport path, but service lifecycle and connectivity become prerequisites. |
| Shared operations with CLI and HTTP adapters | CLI can invoke operations in-process without a server. | An HTTP adapter exposes the operations to remote clients. | Two adapters need compatibility tests; local and remote execution can still differ in identity, resources, and failure modes. |
| Separate CLI-only and API implementations | Each interface can evolve independently. | HTTP clients use a separate implementation. | More freedom, but duplicated behavior creates a greater risk of drift. |

These are design inferences, not measurements of this project. A component boundary does not by itself require a separate process or network call. Independent services can be deployed separately, but remote calls introduce failure and operational concerns ([Lewis and Fowler, Microservices](https://martinfowler.com/articles/microservices.html)).

## What equivalent interfaces need

JSON provides a common representation, not a complete behavioral contract. For each operation, specify its inputs, outputs, validation, side effects, error categories, authorization, and compatibility rules. Decide whether the CLI exposes the same capabilities or only a documented subset.

- **Data and API descriptions:** [JSON Schema](https://json-schema.org/overview/what-is-jsonschema) describes JSON structure and constraints. [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html) describes HTTP interfaces in a language-independent form. Neither guarantees behavior by itself; validate implementations with shared test cases.
- **CLI behavior:** A machine-readable JSON mode can support automation while human-readable output remains useful. Keep result data on stdout, diagnostics on stderr, and use exit codes for success and failure. The [Command Line Interface Guidelines](https://clig.dev/) discuss composability, streams, and JSON output.
- **Errors:** Map common error categories to CLI exit codes and HTTP statuses. For HTTP, [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) defines problem details and the `application/problem+json` media type. Do not assume a CLI exit code is equivalent to an HTTP status; specify the mapping.
- **Versioning:** Define how schemas and operations change, which older clients remain supported, and how incompatible changes are announced. Apply the same compatibility expectations to CLI JSON and HTTP responses.
- **Parity tests:** Run the same input cases against both adapters and compare normalized results, side effects, and error categories. Test permissions and remote failure conditions separately, because in-process tests cannot reproduce all network behavior.

## Distributed execution concerns

### Failures and retries

A remote request can time out after the server has already performed its work. A retry may therefore duplicate a side effect. Define timeouts and retry rules per operation, and use an application-level deduplication strategy for operations that must not run twice. HTTP defines which methods are idempotent, but an application still has to implement the promised semantics ([RFC 9110, idempotent methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2)).

### Long-running agent work

An agent run may outlive a single request. One option is to create a run, return an identifier, and let clients inspect its status, results, and cancellation state. HTTP's `202 Accepted` means processing has been accepted but is not complete; it does not guarantee eventual success ([RFC 9110, 202 Accepted](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3)). Polling is a simple starting point; streaming progress is a separate design choice. Define persistence, cancellation, and restart behavior before treating a run as durable.

### Security and control

An HTTP endpoint that can execute tools or read memory expands the attack surface. Decide who can access each operation and object, what the service can do on their behalf, how credentials are stored, and how resource usage is bounded. Remote access needs transport protection and authentication; local-only endpoints also need a threat model rather than an assumption that every local caller is trusted. The [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) identifies authorization, authentication, resource consumption, and configuration among API risks.

### Data ownership and storage

SQLite is worth evaluating for local state, but adding it to the Brewfile does not make it a distributed database. SQLite's guidance recommends a client/server database when many concurrent writers cannot take turns, and warns about network filesystem latency and locking issues ([When To Use SQLite](https://www.sqlite.org/whentouse.html)). For remote access, consider a service that owns its database rather than having multiple machines directly share a SQLite file. The workshop's actual write patterns and durability requirements are not yet known.

### Tracing and learning

A run that crosses components needs correlation across those boundaries. [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) represent work as spans and use context propagation to correlate spans across processes. Traces can provide evidence for the proposed memory and learning loop, but they do not by themselves decide which lessons are valid or safe to reuse. Retention, redaction, review, and access controls need explicit design.

## Suggested experiment

Prototype one representative operation, such as recording a lesson from a reviewed run. Define its input, result, error categories, and side effects. Implement a local CLI adapter and an optional HTTP adapter over the same operation, then run shared contract tests through both. Test server unavailability, a timed-out write, authorization failure, and a long-running operation separately. Compare setup effort and behavior before deciding whether other components need independent services.

This experiment is a proposal; no implementation or benchmark has been performed.

## Open decisions

1. Which components actually need independent deployment or remote access?
2. Must every CLI operation be available remotely, or can capabilities differ by deployment?
3. What identity and permissions apply when a remote component accesses a local workspace or invokes an agent tool?
4. Where do run state, artifacts, and memory live, and who owns writes?
5. What level of human review is required before a lesson enters reusable memory?
6. What compatibility, observability, and operating costs are acceptable for a four-person team?
