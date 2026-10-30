# State of the Art in LLM Planning

Research notes on how to make LLM agent planning documents more sophisticated and rigorous. Compiled 2026-10-30 from web research; sources are linked inline, and claims from secondary sources are flagged as such.

## Summary

Five findings matter most for improving our agents' planning documents:

1. **LLMs were, until recently, demonstrably weak standalone planners, and the newest frontier models have changed that picture — partially.** The long-standing result (PlanBench, Kambhampati's group) was that even strong models failed simple symbolic planning. A [November 2025 paper](https://arxiv.org/abs/2511.09378) using fresh International Planning Competition tasks found Gemini 3.1 Pro beating the strongest classical planner baseline (245 vs 234 of 360 tasks), though performance still degrades when the problem is obfuscated so the model cannot lean on world knowledge. The safe engineering posture is still: treat the LLM plan as a candidate, not a solution.
2. **External verification beats self-critique.** LLMs are unreliable critics of their own plans; symbolic or programmatic validators are consistently better. This is the single most actionable finding: a planning document should be *checkable*, and something other than the model that wrote it should check it.
3. **Plans should be living artifacts with a re-planning loop,** not one-shot prefaces to execution. The architecture literature converged on hierarchical decomposition with localized re-planning: when a step fails, revise the affected subtree, not the whole plan.
4. **The practice side converged on spec-driven development:** structured, versioned planning documents (spec → plan → tasks) with human review gates between phases, plus a standing "constitution"/rules file the plans must obey.
5. **A plan file doubles as the agent's working memory.** Keeping a continuously rewritten plan/todo file in context ("recitation") measurably helps long-horizon agents stay on goal; the file system serves as external memory for everything else.

## Can LLMs plan? The academic picture

[PlanBench](https://www.alphaxiv.org/abs/2206.10498) (Valmeekam, Kambhampati et al.) established the baseline skepticism: on Blocksworld-style problems, GPT-4-era models generated valid plans at low rates (~33% on cost-optimal planning), and performance collapsed on "Mystery Blocksworld" variants where predicate names are obfuscated — evidence the models were pattern-matching on familiar vocabulary rather than reasoning over state transitions. The maintained [PlanBench leaderboard](https://github.com/karthikv792/LLMs-Planning) shows reasoning models (o1-preview, DeepSeek R1) scoring far higher on plain Blocksworld but still dropping sharply on the obfuscated variants.

Kambhampati's group's response was the **LLM-Modulo framework**: use the LLM as a candidate-plan *generator* inside a loop where model-based critics (symbolic validators, constraint checkers) verify each candidate and feed errors back. Case studies applied it to [travel planning](https://arxiv.org/pdf/2405.20625) and [scheduling](https://www.arxiv.org/pdf/2411.14484). A broader [survey](https://arxiv.org/pdf/2501.04040) frames LLMs as approximate knowledge sources that work best inside verified frameworks rather than as independent planners.

The newest result complicates the skepticism. ["Frontier Large Language Models Rival State-of-the-Art Planners"](https://arxiv.org/abs/2511.09378) (Nov 2025) evaluated Gemini 3.1 Pro and GPT-5 on 360 tasks built from the most recent International Planning Competition, with new tasks created to avoid data contamination and solutions checked by a validator. Gemini 3.1 Pro solved 245 tasks, beating the strongest classical planner baseline (234), and stayed competitive even on obfuscated descriptions; GPT-3.5 solved zero of the same tasks, showing how fast the capability curve moved. The authors conclude the "LLMs can't plan" result no longer holds for frontier models — but note this is one paper, on formal planning domains, and the obfuscated-description drop persists across the literature.

**Takeaway for us:** plan *generation* quality is now good and improving, but it remains most fragile exactly where our use cases live — novel domains the model can't pattern-match, long horizons, and correctness that matters. Verification, not generation, is where rigor should be invested.

## Verification beats self-critique

The clearest negative result in this literature: asking an LLM to critique its own plan does not reliably help, and can hurt.

- [Can Large Language Models Really Improve by Self-critiquing Their Own Plans?](https://arxiv.org/pdf/2310.08118) (Kambhampati's group) found GPT-4 self-critique *diminished* plan-generation performance, traced to the verifier-LLM's own unreliability. Notably, the richness of the feedback didn't matter: binary pass/fail vs. detailed error feedback made no significant difference.
- The ISR-LLM work ([summary](https://www.emergentmind.com/topics/isr-llm)) compared LLM self-validation against a classical symbolic PDDL validator; self-validation was consistently weaker.
- [PDDL-INSTRUCT](https://arxiv.org/pdf/2509.13351) instruction-tunes models for symbolic planning using VAL, a classical plan validator, to check every step against the domain — external validation as training signal.
- [GNNVerifier](https://arxiv.org/pdf/2603.14730v2) argues LLM-based verifiers get misled by *fluent* step descriptions (a well-written wrong plan passes review) and proposes a graph-based structural verifier instead.
- Most of this work targets plan *validity*; plan *quality/optimality* is comparatively neglected (PDDL-INSTRUCT names it as future work).

**Takeaway for us:** rigor in a planning document comes from making it verifiable by something other than its author. Concretely: machine-checkable structure (explicit preconditions, dependencies, success criteria per step), validators or tests where possible, and a *different* context (fresh agent, human, or tool) for review — never the same conversation that produced the plan. Beware fluency: a plan that reads well is not a plan that is right.

## Agent planning architectures

The architecture literature separates planning from execution and localizes failure handling:

- **Plan-and-execute** separates an up-front plan from step execution, replacing pure reactive loops (ReAct) where the agent decides one step at a time and loses the global goal ([overview](https://apxml.com/courses/agentic-llm-memory-architectures/chapter-4-complex-planning-tool-integration/hierarchical-planning-approaches)).
- **Hierarchical decomposition** generates abstract steps first, then decomposes each into concrete sub-steps. The known failure mode is granularity: models struggle to pick the right level of abstraction ([same source](https://apxml.com/courses/agentic-llm-memory-architectures/chapter-4-complex-planning-tool-integration/hierarchical-planning-approaches)).
- **Localized re-planning:** when an action fails, re-plan only the affected subtree rather than discarding the whole plan ([hierarchical planning explainer](https://insertchat.com/glossary/hierarchical-planning)).
- **ReAcTree** ([arXiv 2511.02424](https://papers.cool/arxiv/2511.02424)) makes this concrete: a tree of subgoals, each handled by an LLM agent node that can reason, act, or expand further, with control-flow nodes (sequence/fallback/parallel, per a [secondary summary](https://www.emergentmind.com/topics/reactree)) coordinating execution. It reported 61% goal success on WAH-NL with Qwen 2.5 72B, vs 31% for ReAct. Caveat: embodied-agent benchmarks; the numbers may not transfer to coding agents.

**Takeaway for us:** a rigorous planning document should *be shaped like this architecture*: a hierarchy (goals → sub-goals → steps) with explicit dependencies, so failures can be localized to a subtree, and an explicit re-planning rule ("when a step fails, revise this section and its dependents; do not silently improvise").

## Planning documents in practice: spec-driven development

The practitioner world converged in 2025 on *spec-driven development* — making structured planning documents the primary artifact, with code downstream of them. An [academic treatment](https://arxiv.org/html/2602.00180v1) distinguishes three rigor levels: *spec-first* (write it, then code), *spec-anchored* (spec stays authoritative during maintenance), and *spec-as-source* (humans edit only the spec). Tooling (mostly from [tool roundups](https://www.augmentcode.com/tools/best-spec-driven-development-tools) and practitioner guides, so secondhand):

- **[GitHub Spec Kit](https://github.com/LinkedInLearning/spec-driven-development-with-github-spec-kit-4641001):** a phased `specify → plan → tasks → implement` flow, anchored by a **constitution** file of non-negotiable project rules that every plan must satisfy. Works across Copilot, Claude Code, Gemini CLI. Heavyweight: one spec can produce ~8 files.
- **Kiro (AWS):** lighter; three files per feature under `.kiro/specs/` — requirements (often EARS-format acceptance criteria), design, tasks — plus "steering" documents (product/tech/structure) as the standing rules.
- **Claude Code plan mode** ([official best practices](https://code.claude.com/docs/en/best-practices)): read-only exploration first, a markdown plan the human reviews before any edit, in an Explore → Plan → Implement → Commit cycle. Community variants ([research-plan-implement](https://notesbylex.com/research-plan-implement-workflow), [structured workflow guide](https://feedbagel.com/post/a-structured-workflow-for-using-claude-code-research-plan-implement-methodology)) add persistent markdown artifacts per phase, several human annotation rounds on the plan before implementation, and context-clearing between phases.

Consistent best-practice themes across sources:

1. Write the standing rules file (constitution/steering) *before* the first spec; plans are validated against it.
2. A human review gate between every phase — approve the spec before the plan, the plan before the tasks.
3. Planning documents live in version control, so they persist across sessions and agents, and their evolution is diffable.
4. Separate *what/why* (requirements) from *how* (design) from *execution* (tasks with acceptance criteria).

## Plans as context engineering

For long-horizon work, the plan document is also the agent's working memory:

- **Recitation:** Manus's agent continuously rewrites a `todo.md` inside its context, pushing the global goal back into recent attention on every step — a direct countermeasure to goal drift in long trajectories ([context-engineering deep dive](https://galileo.ai/blog/context-engineering-for-agents); secondhand — the original Manus post wasn't retrieved).
- **File system as external memory:** write intermediate results to files, keep only summaries in context, retrieve by path on demand. [HiAgent](https://arxiv.org/pdf/2408.09559) formalizes the hierarchical version: retain the *results* of finished subgoals, drop their execution details.
- Agents that succeed on long-horizon tasks externalize state — scratchpads, plans, intermediate summaries — rather than holding it in the context window ([Mem0 write-up](https://mem0.ai/blog/working-memory-for-ai-agents); its specific ~5K-token scratchpad threshold is uncited, treat as folklore).

**Takeaway for us:** the plan file should be *updated as execution proceeds* (steps checked off, results recorded, deviations noted), both for human auditability and because the rewriting itself keeps the agent on goal.

## Recommendations

Concrete practices to adopt for the workshop's agents, roughly in order of leverage:

1. **Adopt a phased document pipeline with review gates.** Three artifacts per non-trivial task — requirements (what/why + acceptance criteria), design (how + alternatives considered), tasks (ordered steps with per-step success criteria) — each approved before the next is generated. Start lighter than Spec Kit (Kiro's three-file shape is a good template).
2. **Write a constitution first.** A short, versioned file of non-negotiable rules (conventions, security constraints, review requirements) that every plan is checked against. We partially have this in CLAUDE.md-style files; the upgrade is making plans *explicitly assert* compliance.
3. **Make plans machine-checkable, and never let the author verify.** Give each step explicit preconditions, dependencies, and a verifiable completion criterion (a test, a command, an observable artifact). Review plans in a fresh context — a separate agent, or a human — never the conversation that wrote them. Prefer programmatic validators (tests, linters, schema checks) over LLM judgment wherever one can exist.
4. **Structure plans hierarchically with a re-planning rule.** Goal → sub-goals → steps, dependencies explicit, plus an instruction that failures trigger revision of the affected subtree in the document — not silent improvisation.
5. **Treat the plan as live working memory.** The agent updates the plan file as it executes: check off steps, record results and deviations. This yields both the recitation benefit and an audit trail.
6. **Keep planning documents in git.** Diffable plan evolution is itself a rigor mechanism: it makes scope drift and silent re-planning visible in review.

## Source quality notes

Primary, high-trust: the arXiv papers (PlanBench, LLM-Modulo case studies, self-critique negative result, PDDL-INSTRUCT, HiAgent, ReAcTree, the 2025 IPC evaluation) and Anthropic's Claude Code best-practices page. Secondary and unverified against primaries: the Spec Kit/Kiro comparisons (tool roundups and practitioner blogs), the Manus recitation details, and the Mem0 scratchpad threshold. The ReAcTree control-flow-node details come from an aggregator summary, not the paper itself.
