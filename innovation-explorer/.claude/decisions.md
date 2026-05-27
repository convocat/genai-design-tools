# Decision log

ADR-style log of every deviation from [SPEC.md](./SPEC.md), plus any choice the spec leaves open. SPEC.md is frozen; this file is where changes accumulate.

**Format per entry:**

```
## ADR-NNN — <short title>
*Date · Status: proposed | accepted | superseded by ADR-NNN*

**Context.** What problem / question, what spec section is involved.

**Options considered.**
- A — ...
- B — ...
- C — ...

**Decision.** A, because ...

**Why.** The reasoning that future-readers will need.

**Consequences.** What this commits us to / forbids.

**Code marker.** `# DESIGN-DECISION: ADR-NNN — <one-liner>`
```

Use `/decision <title>` to append a new entry — it assigns the next ID.

---

## Open decisions (need to be resolved before the noted phase)

- **ADR-002** (before Phase 2): Embeddings model — `intfloat/multilingual-e5-large` vs `BAAI/bge-m3` vs other OSS multilingual. Needs benchmark on Dutch government text.
- **ADR-003** (before Phase 0): Docker runtime on Windows — Docker Desktop (license check) vs Rancher Desktop vs Docker Engine on WSL2.
- **ADR-004** (before Phase 1): Cost-gateway lint rule — choose the import-restriction mechanism (ruff `flake8-tidy-imports` ban-relative or a custom AST check or `import-linter`). Recommendation: `import-linter` with a contract that only `backend/app/cost/gateway.py` may import `anthropic`.
- **ADR-005** (before Phase 4): Batch vs sync policy — confirm which call sites route through the Batch API (default: Extractor for crawl backlogs, embedding for backlogs) and which stay sync (chat synthesis, journey steps, the Tier-A query classifier). Document exceptions.
- **ADR-006** (before Phase 4): Model-tier defaults — bind Tier-A / B / C to specific Claude model IDs (verify current names from `https://docs.claude.com`, do not hardcode from memory).
- **ADR-007** (before Phase 2): Redis vs Valkey — Redis ≥7.4 moved to dual SSPL/RSAL. For our self-hosted cache/queue this is acceptable; decide whether to swap for Valkey (true OSS fork) up-front or defer.

---

## Accepted decisions

## ADR-008 — Adopt SPEC v2 (hybrid multi-agent) over v1 (deterministic Celery)
*2026-05-27 · Status: accepted*

**Context.** Two complete specifications were on the table at project start: v1 — a deterministic Celery pipeline with LLM calls embedded in extraction and synthesis; v2 — a hybrid multi-agent system built on the Claude Agent SDK with explicit cost engineering (single gateway, ledger, budget hooks, change-detection cache, extraction cache, prompt caching, Batch API, selective Critic, cheap query routing, answer cache) and a management dashboard. Same product, same schema, same UX, same connectors, same eval intent — different delivery strategy. Choice had to be made before any code, because the two diverge in repo layout, dependencies, and Phase 1 contents.

**Options considered.**
- A — Adopt v2 fully: hybrid multi-agent + cost discipline on Claude Agent SDK.
- B — Keep v1 (deterministic Celery), graft v2's cost layer onto it. Defer multi-agent setup. Easier swap to local Ollama later.
- C — Adopt v2 architecture but swap Claude for local Ollama. Heavy refactor — Agent SDK / MCP / Batch API / prompt caching don't all transfer.

**Decision.** A — Adopt SPEC v2 fully. Archive v1 at `.claude/SPEC-v1.md` for the paper trail.

**Why.** Cost is the binding constraint under the free/OSS hard rule, where LLM API spend is the only allowed paid line item ([[feedback_free_oss_only]]). V2 makes cost discipline structural rather than bolt-on: the single cost gateway, change-detection skip (85-95% of re-crawled documents cost zero LLM tokens), extraction-result cache, prompt caching on the Extractor's static prefix, Batch API for backlogs, selective Critic, and Tier-A cheap-path query routing compound to keep the paid line tolerable. The hybrid principle ("deterministic by default, agentic by exception") prevents the multi-agent setup from sprawling. The management dashboard's what-if estimator lets the operator see the bill before it lands. V1 has none of this structurally; bolting it on would land in roughly the same place with worse coherence. The Anthropic-specific coupling is acceptable precisely because the cost discipline justifies the paid line; if that ever stops being true, this ADR gets superseded.

**Consequences.** Commits to Claude Agent SDK as the agent runtime (no LangGraph/CrewAI/Airflow). Commits to FastMCP for tool servers. Commits to Message Batches API for non-latency-sensitive jobs. Commits to the cost gateway as the single LLM call site (ADR-004 enforces this via lint). Commits to the management dashboard as a first-class surface, not optional. Phase 1 now combines cost gateway + schema (rather than just schema in v1). Adds explicit MCP-servers phase (Phase 3). Adds explicit dashboard phase (Phase 8). Cross-references ADR-001.

**Code marker.** `# DESIGN-DECISION: ADR-008 — SPEC v2 (hybrid multi-agent + cost discipline)` (drop at top of `backend/app/main.py` and `backend/app/agents/orchestrator.py` when those files are first created)

## ADR-001 — LLM provider: Claude with budget caps
*2026-05-27 · Status: accepted*

**Context.** SPEC v2 §2.2 mandates the Claude Anthropic API as the LLM provider. The project's hard constraint is free/OSS only (memory `feedback_free_oss_only`), which makes any paid SaaS dependency a deliberate exception that needs justification.

**Options considered.**
- A — Claude Anthropic API with hard budget caps + cost gateway + cost engineering per SPEC §3.
- B — Local OSS model via Ollama (Llama 3.1 / Mistral / Qwen). No API spend at all.
- C — Hybrid: Claude for high-stakes calls (Tier-C, extraction quality), local for Tier-A bulk scoring.

**Decision.** A — Claude with hard budget caps, single cost gateway, and the §3 cost-engineering discipline (change detection, extraction cache, prompt caching, Batch API, selective Critic, cheap query routing, answer cache).

**Why.** SPEC v2 is architected around Anthropic-specific features (Agent SDK subagents, hooks, MCP integration, Batch API, prompt caching). Their cost effect is what makes the paid line item tolerable: re-crawls of unchanged content cost zero LLM tokens, prompt caching shrinks per-call cost by an order of magnitude on the Extractor, Batch API halves cost on non-latency-sensitive jobs. The free/OSS constraint is honoured for every other component; LLM API spend is the single, controlled, observable exception. Maaike chose this path explicitly on 2026-05-27 when comparing v1 (could swap to Ollama more easily) vs v2 (Anthropic-coupled but cost-disciplined).

**Consequences.** Commits to Claude Agent SDK as the agent runtime. Commits to FastMCP. Commits to the Message Batches API for backlog jobs. Commits to a parametric pricing table in `config.py` that an operator keeps current from the docs. Commits to the cost gateway being the only LLM call site (enforced by ADR-004's lint rule). If Maaike ever wants to swap to a local OSS model, this ADR gets superseded and significant refactor follows.

**Code marker.** `# DESIGN-DECISION: ADR-001 — LLM via Claude API; route via cost/gateway.py`
