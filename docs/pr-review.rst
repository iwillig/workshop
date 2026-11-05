GitHub pull request review (experimental)
=========================================

GitHub pull requests can be reviewed locally by a **normal named agent** using
bounded, read-only research tools. The review is a plain ``workshop agent run``
with a self-contained agent configuration; there is no dedicated PR command.
The workflow does not post reviews or comments to GitHub, does not modify
repositories, and does not execute PR code. Findings require human review.
This is a trusted-local prototype, not a sandbox or a guarantee that the review
found all defects.

Tools and configuration
-----------------------

Three native research tools are defined in ``research_context`` and exposed
through the existing ``llm`` tool system. They are opt-in per agent:

* ``github_get_pr`` fetches bounded PR metadata, including current base and
  head commit SHAs.
* ``github_pr_files`` fetches one bounded page of changed files with available
  patches after checking expected base and head SHAs.
* ``github_read_file`` reads bounded source lines at an explicit commit SHA.

Select tools explicitly in an agent's ``tools`` section. Omitting ``tools``
exposes only workspace built-ins, exactly as before; existing configurations
do not gain GitHub access. A ``GITHUB_TOKEN`` with appropriate read access is
read from the environment when set. ``research-context`` commands load
``.env.local``; plain ``workshop agent run`` does not, so export the token or
use a dotenv-aware workflow as needed.

The named agent in the repository's ``workshop.yaml`` carries its own
system prompt, native model settings, step limit, and only the three GitHub
read tools. Its ``hf-glm`` model ID serves ``zai-org/GLM-5.3-Flash`` through
Hugging Face; see :doc:`agent` for account, token, registration steps, and the
full ``zai-org/GLM-5.3`` alternative. Run from the repository root:

.. code-block:: shell

   pipenv run workshop agent run \\
     --agent pr-reviewer \\
     --task 'Review OWNER/REPO pull request 123; report findings locally.'

The final submission is printed locally. ``--output`` saves an agent
**trajectory**, not a polished report; trajectories may contain sensitive PR
content and credentials that the model provider saw. Progress, token usage,
and the interactive Textual view behave exactly as for other agents, including
supervised Ctrl+C behavior with best-effort cleanup.

Bounded, revision-aware context
-------------------------------

Tool results are deliberately small: a few file entries per page, short
patches, and bounded source line ranges, with explicit ``complete``,
``truncated``, ``next_page``, and ``next_offset`` fields so the agent can page
instead of receiving silent truncation. Repository, PR number, path, SHA,
page, and line-range inputs are validated; arbitrary API URLs are never
accepted. Structured, sanitized errors replace stack traces for HTTP
failures, rate limits, unavailable content, and invalid input.

Source reads require an explicit 40-character commit SHA; branch names and the
local checkout are rejected. ``github_pr_files`` checks the PR's base and head
around each request and fails when they differ from the expected SHAs.
Separate API calls are not atomic, so revision checks reduce but do not
eliminate races. Patches come from GitHub's PR file endpoint; a base-to-head
diff is not verified to match merge-base semantics. Contents reads may
dereference symlinks and do not verify file modes. Fork content may be
unavailable and is reported as an error rather than silently skipped.

The agent's prompt requests the reviewed SHAs and limitations in the final
response, but prompt instructions are not enforcement; check them yourself.
Missing patches, unsupported files, and omissions are visible as explicit
fields, never as clean results.

Security limitations
--------------------

The local agent is **not sandboxed**, and tool calls run without approval.
Tool selection, a read-only token, and prompt instructions are not isolation.
Other same-user processes, trusted plugins, and local credential stores are
outside this workflow's control. PR descriptions, file paths, patches, source,
and tool responses are **untrusted data** that may contain prompt injection or
sensitive content; the configured model provider may receive anything the
agent reads. Use only repositories and providers approved for that data.
There is no guarantee that a review finds every defect.
