# Native workspace storage for agent plans and tasks

## Summary

Notion, Asana, and Shortcut can hold work produced by workshop agents in the tools people already use. Notion supports page content through a Markdown API. Asana exposes tasks and a restricted rich-text format. Shortcut exposes stories and a document API. A workshop storage layer could give agents consistent operations while preserving links to the native objects that people see and edit.

The main design problem is shared ownership. People and agents may change the same content, provider formats differ, and a failed network request may have already created an object. A useful first experiment should create visible native objects, return their URLs, preserve human edits, and report uncertain outcomes. This note is research and a proposal, not a description of implemented write capabilities.

## The idea

An engineer asks an agent to research a topic. The agent creates a plan and follow-up tasks through workshop tools. The plan appears as a readable Notion page and the tasks appear in Asana, linked to the plan. People continue to use those products normally: they can read the work, discuss it, change task state, and edit the plan. A later agent run reads the current native state.

The provider is the authoritative store for shared plans and tasks in this scenario. Workshop may need a small local operation journal for recovery and correlation. A journal is not a second authoritative copy of the plan. Whether that ownership model fits all users is an open question.

A useful distinction is between **transparency to the agent**, which gets consistent operations, and **transparency to people**, who see ordinary pages and tasks with clear provenance. The agent should still receive provider names, URLs, limitations, and errors. Hiding these details would make failures and differences hard to understand.

## Existing workshop capabilities

- `research_context/notion.py` searches accessible Notion pages and retrieves page metadata and nested blocks as JSON. It recursively fetches child blocks. It does not provide writes.
- `research_context/__main__.py` lists Asana project tasks and retrieves individual tasks. It uses `ASANA_ACCESS_TOKEN`; the Notion client uses `NOTION_TOKEN`. These operations are read-only.
- `research_context/github_review.py` and `research_context/github_tools.py` show an existing service and opt-in native `llm.Tool` adapter. The GitHub tools validate inputs, bound output, and return structured errors. They are read-only.
- `workshop/cli.py` composes the component commands. `markdown-it-py` is declared in `Pipfile`. Its parser provides tokens; the [parser documentation](https://markdown-it-py.readthedocs.io/en/latest/using.html) says the default CommonMark configuration does not enable tables or task lists. GFM-like presets and plugins have their own dependencies and behavior.

These are useful starting points, not evidence that a write adapter, task abstraction, or safe Markdown round trip already exists.

## Provider findings

### Notion

[Notion's Markdown guide](https://developers.notion.com/guides/data-apis/working-with-markdown-content.md) documents creating a page with Markdown, reading a page as Markdown, and updating page content. Its recommended `markdown_version: "v2"` uses Notion-flavored Markdown: CommonMark plus GFM tables and task lists, alongside Notion-specific tags. The guide says current API versions default to the deprecated v1 syntax, so a client should select and test the desired version explicitly. Confirm compatibility with the installed Python SDK and chosen Notion API version before implementing; the existing code uses the block API.

The [format reference](https://developers.notion.com/guides/data-apis/notion-flavored-markdown.md) describes headings, lists, to-dos, tables, links and Notion-specific constructs. A general Markdown parser does not automatically preserve those constructs. The Markdown guide also describes unknown blocks, truncation and update warnings. In a batch of targeted edits, some edits may apply while others are skipped and reported as warnings. Asynchronous updates do not return those warnings.

The [update API](https://developers.notion.com/reference/update-page-markdown.md) supports targeted search-and-replace and whole-page replacement. It rejects an ambiguous `old_str` unless replacement of all matches is requested. Targeted text replacement can detect some stale or ambiguous edits; it is not a verified atomic revision check for the whole page. The API also has protections around deleting child pages and databases. An adapter should inspect warnings, unknown blocks and truncation, and avoid silently rewriting a human-edited page.

The [capabilities reference](https://developers.notion.com/reference/capabilities.md) describes separate read, update and insert capabilities. An integration also needs access to the relevant content. The [request limits](https://developers.notion.com/reference/request-limits) describe rate limiting, request size limits and a particularly important case: a write may be saved even when the response is a 503. Read the returned recovery guidance and reconcile before retrying.

### Asana

The [task creation API](https://developers.asana.com/reference/createtask) creates native tasks. The existing workshop integration has task reads but no task creation or update path. Tasks, assignees, due dates, project membership and completion state have meanings in the team's workflow; they should remain structured fields instead of being inferred from document text alone.

[Asana rich text](https://developers.asana.com/docs/rich-text.md) uses `html_notes` for formatted task descriptions and supports a defined subset of HTML. It is not a general Markdown document API. A Markdown-to-Asana renderer needs an explicit supported subset and a policy for unsupported content, especially tables and provider-specific markup. Use links to the full plan where appropriate rather than assuming every plan can be reproduced in a task description.

Asana [rate-limit guidance](https://developers.asana.com/docs/rate-limits.md) requires respecting `Retry-After` for 429 responses and cautions about duplicate POST creates. A timeout or error after sending a create needs reconciliation; a retry must not be assumed safe.

### Shortcut

The [Shortcut API](https://developer.shortcut.com/api/rest/v3) provides native stories, workflows, tasks and documents. Its Doc API accepts Markdown or HTML, converts Markdown input to HTML for storage, and can return Markdown. The create and update documentation says input defaults to HTML if `content_format` is omitted, so callers sending Markdown must specify it. Returned Markdown should not be assumed to be byte-identical to the input.

Shortcut is a plausible future adapter for tasks and, separately, documents. Story states and workflow configuration need provider-specific mapping. Its full object model and permissions require further validation before committing to a shared task contract.

## Design direction

### Separate documents from tasks

A research plan and a task have different semantics. A document contains sections, citations and tables. A task has workflow state, ownership, due dates and project membership. Model them as related capabilities, not as interchangeable blobs:

- **Document operations:** create a plan, read it, and make a bounded edit to a known section or text range.
- **Task operations:** create, read and list tasks; update explicitly selected fields or state.
- **Links:** return provider, object ID and native URL for every created object; associate tasks with their source plan using a visible link where the provider supports it.

Provider adapters should advertise capabilities. Unsupported operations or formatting must return a clear error or an explicit conversion warning. A common core can coexist with provider-specific extensions. Cross-provider identity, workflow state mapping and permission behavior need contracts before implementation.

### One operation, multiple interfaces

A possible structure is:

```text
CLI command ───────┐
                   ├─> document/task operations ─> provider adapter ─> API
Native LLM tool ───┘
```

The shared operation would own validation, provider selection, permissions, conversion and error handling. The CLI and native tool would adapt inputs and results to their callers. The existing GitHub service/tool pattern is a useful reference, although its read-only safety properties do not carry over to writes. Shared contract tests should check that both interfaces produce equivalent outcomes. See [component interfaces](component-interfaces.md) for related local and remote interface trade-offs.

Illustrative operation names, not implemented commands:

```text
plan.create(title, markdown, destination) -> provider, id, url, warnings
task.create(title, project, plan_url, fields) -> provider, id, url
task.get(id) -> current fields, provider, url
plan.update_section(id, expected_content, replacement) -> outcome, warnings
```

`expected_content` describes a possible conflict check, not a guarantee of atomic compare-and-swap. The adapter must document what its provider can actually enforce.

### Define the Markdown contract

Start with a named, tested subset: headings, paragraphs, links, emphasis, lists, fenced code and tables. Specify how task-list checkboxes behave: a checkbox in a Notion page is a document block, while an Asana or Shortcut task is a separate object with its own identity and state. Do not silently create tasks from every checkbox.

Use parser tokens to validate and identify sections where needed. Enable table and task-list support explicitly and test the installed version. For Notion, compare direct use of its v2 Markdown endpoint against a block renderer before building a conversion layer. Provider-specific tags, mentions, citations, attachments and unknown blocks need explicit handling. Reject a write or surface a warning when fidelity cannot be preserved. Test semantic round trips and native display; identical Markdown bytes are not a realistic general guarantee.

### Handle concurrent edits and partial failures

The workshop must treat native content as shared, mutable state:

1. Read the current object and its completeness and warning indicators before an edit. Keep the provider ID, URL and available edit metadata.
2. Prefer narrow updates. Compare the expected target content with current content and stop on a conflict. A read followed by a write has a race unless the provider enforces a conditional update; test and document that limit.
3. Never replace a whole page from a truncated or lossy representation. Preserve content outside the intended edit, including human-authored sections and provider-specific blocks.
4. Record an operation ID and known provider IDs before and after side effects. After an ambiguous create timeout, reconcile using provider-supported lookup or a durable marker if available. If the result cannot be established, return `unknown` and ask the engineer to resolve it; do not claim exactly-once creation.
5. Treat plan creation and task creation as separate remote operations. Report each success, failure and unknown outcome with object links. Do not imply a distributed transaction or automatically delete already-created work after partial failure.

Provider-specific guarantees and limits need live tests. For example, a local journal alone cannot prove that a remote create did not happen when the response was lost.

### Security and trust

Native writes affect shared workspaces. Scope each integration to approved destinations and the minimum capabilities it needs. Return the target workspace, project or page and intended changes before a write when the engineer's policy requires review. This is a proposed policy choice; the existing agent executes tools without per-call approval, as documented in `docs/agent.rst`.

Treat page contents, task descriptions, comments and attachments as untrusted input. They may contain instructions intended to redirect an agent. Provider content is task data, not authority to change the agent's instructions or grant new permissions. Bound outputs, validate destinations, protect credentials and avoid logging sensitive content unnecessarily. A model provider may receive any content given to the model. Existing local execution is not sandboxed.

Human visibility also has a cost: a shared page or task may trigger notifications, expose sensitive research to other workspace members, or create noise. Test in a dedicated project and make authorship and links visible.

## Recommended experiment

Use one dedicated Notion parent page and one Asana test project. Obtain permission to write there and use synthetic content. The experiment should answer whether native artifacts are useful to people and safe to update, before adding a general-purpose storage framework.

1. Create a research plan in Notion containing a heading, links, a list and a small table. Read it back and inspect the page in the UI. Verify SDK and API version support for Notion-flavored Markdown v2.
2. Create one Asana task with a link to the plan. Return both native URLs. Inspect the task in Asana and check that its project, author and formatting are understandable.
3. Make a human edit to the Notion page and an Asana task field. Read both again and verify that a later narrow agent update preserves those edits. Test a conflicting edit, duplicate matching text, warnings and an unsupported or unknown block.
4. Simulate timeouts after a provider accepts a create, partial multi-object completion, permission failures and rate limits. Confirm that unknown outcomes are reported and no blind create retry occurs.
5. Expose the same operations through a CLI and an opt-in native tool over the shared service. Test parity with fakes; validate provider behavior separately in the dedicated workspace.
6. Have an engineer judge whether the resulting artifacts are readable, discoverable and useful to existing workspace users. Record provider calls, conversion warnings and any manual recovery required.

This experiment requires write access and explicit decisions on destination, approval and data handling. No live API writes or provider integration tests were performed for this research.

## Questions for design

1. Which artifacts should be visible immediately, and which should remain drafts until the engineer publishes them?
2. Does an agent own a designated page or section, or may it edit any page the integration can access?
3. Who can create or complete tasks, assign people, and change due dates? Which actions require review?
4. Are Notion and Asana always the source of truth, or is offline operation and later synchronization required?
5. Which project and page destinations are allowed, and how are they selected per repository or agent?
6. Which formatting must survive edits, and what should happen when a provider cannot represent it?
7. How should a task link back to its plan, and how should changes to the plan affect existing tasks?
8. What should users see about agent authorship, uncertainty, and supporting evidence?
9. Which provider-specific fields and workflow states must remain available through the shared interface?
