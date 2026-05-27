# SPEC v2 — GovInnovatie GraphRAG Explorer (hybrid multi-agent)
> Alternative architecture for the same product as SPEC v1: a GraphRAG chatbot
> and interactive explorer for the digital innovation landscape of the Dutch
> government. Where v1 is a deterministic pipeline, **v2 is a hybrid
> multi-agent system**: a deterministic, zero-LLM-cost spine for high-volume
> mechanical work, and a roster of specialised agents (built on the Claude
> Agent SDK) only where judgement is genuinely needed.
>
> This document is the build specification. It is written to be handed
> directly to Claude Code. It is self-contained — you do not need v1 to build
> from this file.
>
> **Cost is a primary design constraint.** The corpus is large and re-crawled
> regularly. Section 3 is the cost model; every agent definition states its
> cost profile. Treat cost engineering as a feature, not an afterthought.

> **This file is FROZEN as the contract.** Do not edit it. All deviations go to
> `.claude/decisions.md` instead. Frozen on 2026-05-27. v1 archived at
> `.claude/SPEC-v1.md`.

---
## 0. How to use this document (instructions for Claude Code)
You are building the system described below. Work in phases (Section 14). After
each phase, stop, run the phase's acceptance checks, and summarise what was
built before continuing.
Ground rules:
- **Hybrid principle is non-negotiable.** Before making any step an "agent",
  ask: does this step require judgement? If it is mechanical (fetching,
  hashing, chunking, embedding, graph traversal, vector search), it MUST be
  deterministic code with no LLM call. Agents are expensive; spend them only on
  judgement. Leave a `# COST:` comment at every LLM call site stating which
  model tier it uses and why.
- **Cost is observable and capped.** Every LLM call goes through one
  `llm_gateway` module that logs tokens, cached tokens, model, agent, run, and
  estimated cost to a `cost_ledger` table, and enforces budget caps. No agent
  calls a model directly.
- **Language:** corpus and UI copy are Dutch; code, comments, identifiers,
  commit messages, agent prompts are English. Extraction prompts must instruct
  the model to keep entity names in original Dutch.
- **Determinism & idempotency:** ingestion and graph-building must be
  re-runnable. Running ingestion twice on unchanged sources must produce zero
  new LLM calls and zero duplicate nodes/edges.
- **Typed everywhere.** Python: full type hints + Pydantic. TypeScript: strict,
  no `any`.
- **No secrets in the repo.** Credentials via env vars; provide `.env.example`.
- **Verify product facts.** Do not hardcode model IDs or prices from memory.
  Read current model names, IDs, context limits, Batch API details, and
  prompt-caching behaviour from the official docs
  (`https://docs.claude.com/en/docs_site_map.md`) and put them in `config.py`.
- **Test as you go.** Connectors, extractors, retrieval, cost gateway, hooks
  all get unit tests. Target ≥70% coverage on `ingestion/`, `agents/`,
  `graph/`, `cost/`.
- When a decision is ambiguous and unspecified, choose the cheaper and simpler
  option, leave a `# DESIGN-DECISION:` comment, and continue.
---
## 1. Product summary
### 1.1 What it is
An application that lets a user — typically an external consultant or civil
servant new to the Dutch government innovation landscape — explore which
digital innovation initiatives exist, how they relate, who runs them, where the
code and rules live, and what was learned. It delivers this through a GraphRAG
chat interface, an interactive knowledge-graph explorer, structured search,
guided journeys, and an open research mode.
### 1.2 The five required capabilities
| #    | Capability                                                  | Where specified           |
| ---- | ----------------------------------------------------------- | ------------------------- |
| 1    | Ingest source content on a regular schedule                 | Sections 4 (Harvester), 6 |
| 2    | Discover new sources and update automatically               | Section 4 (Scout)         |
| 3    | Build a knowledge graph usable standalone and for retrieval | Sections 7, 8             |
| 4    | Fixed journeys + open research/exploration                  | Section 11                |
| 5    | Best-in-class UX for search, retrieval, learning, synthesis | Section 12 (app)          |
Plus, on top of v1: a **management dashboard** for operations and cost
(Section 12.8 / Section 13).
### 1.3 Non-goals (v1 of this build)
No write-back to government systems. No auth beyond a single shared deployment.
Single-tenant. Responsive web only (no native mobile).
---
## 2. Architecture overview
Two planes of agents around one orchestrator, sitting on a deterministic spine,
with MCP tool servers over the storage layer, and a hook-fed management
dashboard.
```
┌──────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR AGENT  — routes, plans, enforces budget          │
├───────────────────────────┬──────────────────────────────────┤
│  KNOWLEDGE PLANE           │  QUERY PLANE                      │
│  keeps the graph fresh     │  serves the user                  │
│  · Scout                   │  · Planner                        │
│  · Harvester (mostly       │  · Retrieval squad (3 subagents,   │
│    deterministic)          │    mostly deterministic)          │
│  · Extractor               │  · Synthesizer                    │
│  · Critic (selective)      │  · Journey agent                  │
│  · Graph steward           │  · Research agent                 │
├───────────────────────────┴──────────────────────────────────┤
│  DETERMINISTIC SPINE  (no LLM cost)                            │
│  fetch · robots · dedup · chunk · embed · change-detection ·   │
│  graph traversal · vector search · BM25                        │
├──────────────────────────────────────────────────────────────┤
│  MCP TOOL SERVERS   Graph · Vector · Web · GitHub · SQL        │
├──────────────────────────────────────────────────────────────┤
│  STORAGE   Neo4j · Qdrant · PostgreSQL · object store          │
└──────────────────────────────────────────────────────────────┘
        ↕  Hooks → cost ledger, telemetry → MANAGEMENT DASHBOARD
```
### 2.1 The hybrid principle
The system is **deterministic by default, agentic by exception**. Most of the
work — fetching, hashing, deduplicating, chunking, embedding, graph traversal,
vector and keyword search — is plain code with zero LLM cost. Agents are
invoked only where the task requires judgement: deciding whether a discovered
source is relevant, extracting entities and relations from prose, resolving
whether two entities are the same, planning how to answer a complex question,
and synthesising a cited answer. This is what keeps a large corpus affordable.
### 2.2 Technology choices
Defaults below. Deviate only with a `# DESIGN-DECISION:` comment.
| Concern            | Choice                                                       | Notes                                                        |
| ------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| Backend language   | Python 3.12                                                  | Ingestion, agents, graph, API                                |
| Frontend           | TypeScript + Next.js 14 (App Router)                         | UI                                                           |
| Agent runtime      | **Claude Agent SDK** (`claude-agent-sdk`)                    | Subagents via `AgentDefinition`; hooks (`PreToolUse`, `PostToolUse`, `SessionStart`); MCP support; sessions. This is what makes the system standalone — no LangGraph/CrewAI/Airflow. |
| LLM provider       | Anthropic API                                                | Three model tiers, see Section 3. IDs in config.             |
| Bulk LLM jobs      | **Message Batches API**                                      | Extraction/embedding backlogs run as batch jobs (~50% cheaper, non-latency-sensitive). |
| Graph database     | Neo4j 5 (Community)                                          | Cypher; abstract behind a `GraphStore` interface.            |
| Vector store       | Qdrant                                                       | Standalone, good filtering.                                  |
| Relational store   | PostgreSQL 16                                                | Sources, documents, chunks, runs, queues, journeys, chat, **cost ledger**, extraction cache. |
| Object store       | MinIO (S3-compatible)                                        | Raw document snapshots.                                      |
| Scheduler / queue  | Celery + Redis (beat for cron)                               | Scheduled crawls, batch jobs.                                |
| MCP servers        | FastMCP                                                      | One server per tool domain (Section 5).                      |
| Embeddings         | Multilingual model with strong Dutch support                 | Configurable; cached per chunk hash.                         |
| API framework      | FastAPI                                                      | Backend HTTP API + SSE streaming.                            |
| Frontend graph viz | Sigma.js + graphology (overview), Cytoscape.js (detail)      | See 12.4.                                                    |
| Containerisation   | Docker + docker-compose                                      | One command runs the whole stack.                            |
| Observability      | Structured JSON logs + OpenTelemetry traces + `/health`, `/metrics` | Hooks feed the dashboard.                                    |
### 2.3 Repository layout (monorepo)
```
govinnovatie-explorer/
├── docker-compose.yml
├── .env.example
├── README.md
├── SPEC.md                       ← this file
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py             ← settings, model tiers, budgets, pricing
│   │   ├── api/
│   │   ├── cost/
│   │   │   ├── gateway.py         ← the single LLM call site
│   │   │   ├── ledger.py          ← cost_ledger writes + queries
│   │   │   └── budget.py          ← per-run / per-day / per-agent caps
│   │   ├── agents/
│   │   │   ├── orchestrator.py
│   │   │   ├── definitions.py     ← AgentDefinition for every subagent
│   │   │   ├── prompts/           ← one file per agent system prompt
│   │   │   ├── scout.py
│   │   │   ├── extractor.py
│   │   │   ├── critic.py
│   │   │   ├── steward.py
│   │   │   ├── planner.py
│   │   │   ├── synthesizer.py
│   │   │   ├── journey.py
│   │   │   └── research.py
│   │   ├── mcp/                   ← FastMCP servers
│   │   │   ├── graph_server.py
│   │   │   ├── vector_server.py
│   │   │   ├── web_server.py
│   │   │   ├── github_server.py
│   │   │   └── sql_server.py
│   │   ├── ingestion/             ← deterministic spine
│   │   │   ├── connectors/
│   │   │   ├── fetch.py           ← robots, rate-limit, conditional GET
│   │   │   ├── normalise.py
│   │   │   ├── chunk.py
│   │   │   ├── embed.py
│   │   │   ├── change_detect.py
│   │   │   └── pipeline.py
│   │   ├── extraction/
│   │   │   ├── schema.py          ← entity/relation types (Section 7)
│   │   │   ├── cache.py           ← extraction result cache
│   │   │   └── resolver.py        ← deterministic-first entity resolution
│   │   ├── graph/
│   │   │   ├── store.py
│   │   │   ├── writer.py
│   │   │   ├── community.py       ← incremental community detection
│   │   │   └── export.py
│   │   ├── retrieval/
│   │   │   ├── hybrid.py
│   │   │   ├── graphrag.py
│   │   │   └── classify.py        ← cheap query router (Section 10.1)
│   │   ├── hooks/                 ← Agent SDK hooks (Section 9)
│   │   ├── models/
│   │   └── tasks/                 ← Celery tasks
│   └── tests/
├── frontend/
│   ├── app/                       ← Next.js App Router (incl. /dashboard)
│   ├── components/
│   └── lib/
└── data/
    └── seed/                      ← seed source registry + canonical orgs
```
---
## 3. Cost engineering (read this before building anything)
The corpus is large and re-crawled on a schedule. Naively running an LLM agent
over every document on every crawl would dominate the running cost. The
following techniques are **mandatory**, not optional. The dashboard
(Section 12.8) must make their effect visible.
### 3.1 Model tiering
Three tiers, exact model IDs in `config.py` (verified against current docs):
| Tier                  | Model family | Used for                                                     |
| --------------------- | ------------ | ------------------------------------------------------------ |
| **Tier A — fast**     | Haiku class  | High-volume, low-judgement calls: candidate relevance scoring (Scout), query classification (Planner router), the Critic's first-pass rule checks, simple entity linking. |
| **Tier B — standard** | Sonnet class | The workhorse: entity/relation extraction, entity resolution, normal answer synthesis, most agent reasoning, journey steps. |
| **Tier C — premium**  | Opus class   | Rare, high-stakes only: complex research decomposition (Planner), schema-evolution proposals (Graph steward), hard conflict resolution, final synthesis of open-research briefs. |
Every LLM call site declares its tier. Default to the cheapest tier that does
the job; escalate only with a recorded reason. The tier mix per agent is shown
in Section 4.
### 3.2 The deterministic spine costs nothing
Fetching, robots handling, rate limiting, content hashing, deduplication,
boilerplate stripping, language detection, chunking, embedding, change
detection, graph traversal, vector search, and BM25 are all plain code. No LLM
call. This is the majority of the work by volume. Embedding has a per-token API
cost but it is one or two orders of magnitude below generation cost — still,
cache it (3.6).
### 3.3 Change detection is the single biggest lever
On a re-crawl, most documents are unchanged. The pipeline computes a
`content_hash` for every fetched document. **If the hash is unchanged since the
last run, the document skips extraction entirely** — zero LLM cost. Only
genuinely new or changed documents reach the Extractor. For a stable
government corpus, expect 85–95% of documents to be unchanged on any given
weekly crawl. Implement this in `change_detect.py` and make the skip rate a
headline dashboard metric.
### 3.4 Incremental crawl scheduling
Do not crawl everything daily. Each source carries a `schedule` (`daily` /
`weekly` / `monthly`) set by how fast it actually changes:
- Tier-1 registries (Algoritmeregister, Innovatiebudget): monthly or weekly.
- Institutional pages: weekly.
- Trade media (used for freshness/discovery): daily, but these are short.
A crawl that finds nothing changed costs effectively zero LLM tokens (see 3.3).
### 3.5 Extraction result cache
Extraction output is cached in an `extraction_cache` table keyed by
`hash(content_hash + schema_version + extractor_prompt_version + model_id)`.
Re-running extraction never re-pays unless the document, the schema, the
prompt, or the model changed. A schema change triggers a controlled, batched
re-extraction (3.8) — not an uncontrolled storm.
### 3.6 Prompt caching
The Extractor's system prompt, the full entity/relation schema, and the
few-shot examples are identical across thousands of extraction calls. Use the
API's prompt-caching feature so this large static prefix is written to cache
once and read cheaply thereafter. The same applies to the Critic and any agent
with a stable, large system prompt. Verify current prompt-caching mechanics and
minimum cacheable size against the docs; structure prompts so the static prefix
comes first and the variable document content comes last. Embedding-cache and
prompt-cache hit rates are dashboard metrics.
### 3.7 Batch API for backlogs
Extraction and embedding of a crawl backlog are not latency-sensitive. Route
them through the **Message Batches API**, which is materially cheaper than the
synchronous API. Real-time chat and journey runs stay on the synchronous,
streaming API. The pipeline accumulates changed documents from a crawl into a
batch job rather than firing one synchronous call per document.
### 3.8 Controlled re-extraction on schema change
When the Graph steward's schema-evolution proposal is approved, the affected
documents must be re-extracted. Do this as a single, budgeted, off-peak Batch
API job with a progress bar on the dashboard — never as an implicit cascade.
### 3.9 The Critic is selective, not exhaustive
Running the Critic on every extraction roughly doubles extraction cost. Instead
the Critic reviews:
- **All** extractions where the Extractor self-reported low confidence
  (the Extractor returns a `confidence` per entity/relation).
- A **configurable random sample** (default 5%) for drift detection.
- **Any** extraction that introduces a fact conflicting with an existing
  tier-1 graph fact.
Most of the Critic's checks are deterministic rules (schema conformance,
provenance present, controlled-vocabulary values) and run with no LLM call at
all; only borderline cases escalate to a Tier-A or Tier-B model. Sampling rate
and the confidence threshold are config values surfaced on the dashboard.
### 3.10 Cheap query routing
Most user questions are simple and local ("who runs ChatAmsterdam?"). The
Planner's first action is a **Tier-A query classifier** that routes:
- **Simple/local** → a single deterministic hybrid-retrieval call + one Tier-B
  synthesis call. No multi-agent loop.
- **Complex/global** → the full agentic research loop.
This keeps the median question cheap and reserves expensive multi-agent
reasoning for the questions that need it. Answer caching (3.11) reduces it
further.
### 3.11 Answer & journey-output caching
Synthesised answers to recurring questions and the outputs of fixed journey
steps are cached, keyed by the question (normalised) plus the set of graph node
versions they depend on. The cache is invalidated when any dependency node
changes. Frequently asked onboarding questions then cost nothing to re-serve.
### 3.12 Delta-extraction for cross-source duplicates
The same initiative is often described on several sites. Extract fully from the
highest-trust source. For lower-trust sources covering an entity already in the
graph, run a cheap Tier-A "does this document add any new fact?" check; only
escalate to full extraction if it does. Otherwise attach the document as
provenance (`MENTIONS`) without paying for full extraction.
### 3.13 Budget enforcement via hooks
A `PreToolUse` hook checks the running `cost_ledger` before every LLM call
against three caps: **per-run**, **per-day**, and **per-agent**. When a cap is
reached the system **degrades gracefully** — the remaining work is queued for
the next window and the run finishes cleanly — rather than failing or silently
overspending. Caps are config values, editable from the dashboard. The Scout in
particular is hard-bounded (max N candidate evaluations per run) because
open-ended discovery is the easiest place to burn money.
### 3.14 The cost ledger
Every LLM call — no exceptions — goes through `cost/gateway.py`, which writes a
`cost_ledger` row: timestamp, agent, run_id, model_id, input tokens, output
tokens, cached tokens, batch-vs-sync, and estimated cost (computed from the
pricing table in config). The dashboard reads this ledger for all cost views.
A call that does not go through the gateway is a bug; add a lint/test check
that no module imports the Anthropic client directly except the gateway.
### 3.15 Parametric cost model
Do not hardcode prices. `config.py` holds a pricing table (per-model
input/output/cached/batch rates) that an operator updates from current docs.
Build a `cost/estimate.py` that, given corpus size, expected change rate,
crawl cadence, sampling rates, and the pricing table, produces an estimated
monthly run cost — and expose it on the dashboard as a "what-if" panel so the
operator can see the effect of, e.g., raising the Critic sample rate before
they commit to it.
---
## 4. The agents
Each agent is an `AgentDefinition` (Claude Agent SDK subagent) with its own
system prompt, its own MCP tool allowlist, and its own isolated context window.
Agents never call a model directly — every call goes through `cost/gateway.py`.
For each agent below: **role**, **plane**, **default model tier**, **tools**,
**trigger**, **cost profile**.
### 4.1 Orchestrator
- **Plane:** cross-cutting. **Tier:** B (short context, infrequent).
- **Tools:** SQL MCP (read run state), spawns subagents.
- **Trigger:** every scheduled knowledge-plane run; every user request.
- **Role:** decides which plane and which agents handle the work, sequences
  subagents, and is the holder of the per-run budget. Keeps its own context
  small — it sees summaries from subagents, never raw documents.
- **Cost profile:** low. Reasoning over short summaries only.
### 4.2 Scout — source discovery (capability 2)
- **Plane:** knowledge. **Tier:** A for candidate scoring, B for the final
  relevance judgement on shortlisted candidates only.
- **Tools:** Web MCP (search/fetch), SQL MCP (read source registry, write to
  review queue).
- **Trigger:** weekly scheduled run.
- **Role:** collects candidate sources from (a) outbound links found in already
  ingested tier-1/2 documents and (b) a small curated set of search queries.
  Scores each candidate against an inclusion rubric: *is this a Dutch
  public-sector digital-innovation initiative, organisation, community,
  repository, or framework?* Writes candidates to the discovery review queue.
- **Cost controls:** hard cap on candidates evaluated per run; Tier-A for the
  bulk score, Tier-B only for the shortlist; conservative — precision over
  recall. Auto-enable only for `github_org` and `generic_html` connectors on
  `*.overheid.nl`; everything else waits for human approval in the dashboard.
### 4.3 Harvester — fetching (capability 1)
- **Plane:** knowledge. **Tier:** mostly **no LLM** (deterministic); Tier-A
  only as an exception.
- **Tools:** the deterministic `fetch.py` + connectors; Web MCP for the
  exception path.
- **Trigger:** each source on its schedule.
- **Role:** fetches documents politely (robots.txt, descriptive User-Agent,
  per-domain rate limit, exponential backoff, conditional GET), stores raw
  snapshots, and runs change detection. **Crawling is deterministic.** The
  agentic path is invoked only when a known source's page structure has changed
  and the connector can no longer parse it — then a one-off Tier-A call derives
  an updated parse strategy, which is saved to the source config so the next
  crawl is deterministic again.
- **Cost profile:** near zero in steady state.
### 4.4 Extractor — entities & relations (capability 3)
- **Plane:** knowledge. **Tier:** B. The main LLM cost centre.
- **Tools:** none — it receives clean chunks and returns structured output via
  a tool schema (forced JSON, no wasted prose tokens).
- **Trigger:** only on new or changed documents (change detection, 3.3) and
  cache misses (3.5).
- **Role:** extracts entities and relations conforming to the Section 7 schema;
  returns a `confidence` per item; keeps Dutch entity names verbatim.
- **Cost controls:** change detection, extraction cache, prompt caching for the
  static schema/examples prefix, Batch API for crawl backlogs, delta-extraction
  for cross-source duplicates. This is where most of 3.3–3.12 pays off.
### 4.5 Critic — groundedness QA
- **Plane:** knowledge. **Tier:** mostly **deterministic rules**; A/B for
  borderline cases.
- **Tools:** Graph MCP (check facts against existing graph).
- **Trigger:** selectively (3.9) — low-confidence extractions, a 5% sample,
  and tier-1 conflicts.
- **Role:** verifies each extracted claim is schema-conformant, has provenance,
  uses controlled-vocabulary values, and is supported by the source text;
  rejects or flags those that are not. Implements the SDK's "agent evaluates
  its own work" pattern as a separate reviewer so failures are caught before
  they reach the graph.
- **Cost controls:** rules first (free), LLM only for genuine ambiguity;
  sampling rate configurable.
### 4.6 Graph steward — resolution & schema evolution
- **Plane:** knowledge. **Tier:** B for entity resolution; C for schema-
  evolution proposals (rare).
- **Tools:** Graph MCP, SQL MCP (canonical-org table, merge & schema queues).
- **Trigger:** after each extraction batch.
- **Role:** resolves whether an extracted entity matches an existing node
  (deterministic exact/alias/fuzzy match first; LLM only for genuine
  ambiguity), routes uncertain merges to the dashboard merge queue, resolves
  property conflicts using trust tier + recency, and — when it repeatedly
  encounters entities that do not fit the schema — drafts a schema-evolution
  proposal for human approval on the dashboard.
- **Cost controls:** deterministic resolution handles the large majority;
  Tier-C is reserved for the rare schema proposal.
### 4.7 Planner — query understanding (capability 4/5)
- **Plane:** query. **Tier:** A for the classifier; C only for complex
  decomposition.
- **Tools:** SQL MCP (journey definitions).
- **Trigger:** every user question.
- **Role:** classifies the question (simple/local vs complex/global vs
  journey), and for complex questions decomposes it into sub-questions and a
  retrieval plan.
- **Cost controls:** the Tier-A classifier (3.10) keeps most questions on the
  cheap path; Tier-C decomposition only for genuinely complex research.
### 4.8 Retrieval squad — graph / vector / web
- **Plane:** query. **Tier:** mostly **deterministic**; Tier-A only for entity
  linking.
- **Tools:** Graph MCP, Vector MCP, Web MCP — three subagents, dispatched in
  parallel, each with its own isolated context so raw results do not bloat the
  Planner's window.
- **Trigger:** dispatched by the Planner.
- **Role:** graph-traversal retrieval, vector-semantic retrieval, and (only
  when freshness is required) web retrieval. Results are fused with Reciprocal
  Rank Fusion deterministically.
- **Cost profile:** near zero — search and traversal are deterministic; only
  entity linking may need a cheap call.
### 4.9 Synthesizer — cited answers (capability 5)
- **Plane:** query. **Tier:** B for normal answers; C for open-research briefs.
- **Tools:** Graph MCP (pull provenance for citations).
- **Trigger:** after retrieval.
- **Role:** composes the answer, cites every fact with URL + trust tier +
  `observed_at`, flags conflicts, never asserts an uncited fact, offers
  graph-anchored follow-ups.
- **Cost controls:** answer caching (3.11); Tier-C reserved for long research
  briefs.
### 4.10 Journey agent — guided flows (capability 4)
- **Plane:** query. **Tier:** B.
- **Tools:** Graph MCP, Vector MCP, SQL MCP.
- **Trigger:** when the user runs a journey.
- **Role:** executes a declarative journey definition (Section 11) step by
  step. Because journeys are structured, steps are cheap and cacheable.
### 4.11 Research agent — open exploration (capability 4)
- **Plane:** query. **Tier:** B, with C for final synthesis.
- **Tools:** Graph MCP, Vector MCP, Web MCP; can trigger on-demand ingestion of
  a known-but-uningested source.
- **Trigger:** complex/open questions routed by the Planner.
- **Role:** runs a bounded agentic loop — decompose, retrieve per sub-question,
  identify gaps, optionally ingest a missing source, synthesise a structured
  cited brief.
- **Cost controls:** hard caps on sub-questions and tool calls; the per-run
  budget hook applies; progress streamed to the UI.
### 4.12 Watchdog — operations (no LLM)
- **Plane:** cross-cutting. **Tier:** none — deterministic.
- **Role:** consumes hook events and the cost ledger, computes health and cost
  metrics, raises alerts, and feeds the management dashboard. Pure code.
---
## 5. MCP tool servers
Agents reach storage only through MCP servers (FastMCP). Adding a capability
means adding a server, not editing agents.
| Server         | Wraps          | Key tools (read-only unless noted)                           |
| -------------- | -------------- | ------------------------------------------------------------ |
| **Graph MCP**  | Neo4j          | `get_node`, `get_neighbourhood`, `traverse`, `shortest_path`, `find_by_type`, `upsert_node`/`upsert_edge` (write — knowledge plane only), `community_summary` |
| **Vector MCP** | Qdrant         | `semantic_search` (with trust-tier / recency filters), `get_chunks` |
| **Web MCP**    | search + fetch | `web_search`, `fetch_url` (politeness enforced), used by Scout and Research agent |
| **GitHub MCP** | GitHub API     | `list_org_repos`, `get_repo`, `get_readme` — for the `github_org` connector |
| **SQL MCP**    | PostgreSQL     | `query_sources`, `read_queue`, `write_queue`, `read_journeys`, `read_cost_ledger` — scoped, allowlisted statements only |
Write tools (graph upserts, queue writes) are exposed only to the agents that
need them; the query plane's agents get read-only allowlists. Enforce this in
each `AgentDefinition`'s tool list, not by convention.
---
## 6. Deterministic spine — ingestion pipeline
Zero LLM cost. Per source, per scheduled run:
```
1. RESOLVE TARGETS   connector.discover_urls()  → CrawlTarget[]
2. FETCH             fetch.py: robots, rate-limit, conditional GET, backoff
3. CHANGE DETECT     compute content_hash; unchanged → STOP (no further cost)
4. SNAPSHOT          store raw doc in object store
5. NORMALISE         strip boilerplate, detect language, ISO-normalise dates,
                     canonicalise org names
6. CHUNK             semantic chunking; a structured record is one chunk
7. EMBED             embed each chunk (cache by chunk hash) → Qdrant
8. QUEUE FOR EXTRACTION   add changed docs to the next Batch API extraction job
9. RECORD RUN        write IngestionRun row: counts, skip rate, errors, duration
```
Steps 8 onward hand off to the knowledge-plane agents (Extractor → Critic →
Graph steward), which run as a batched job (3.7). Steps 1–9 are Celery tasks; a
per-source run is a Celery chain; fetches fan out in a group. A failure on one
target collects an error and continues — it never aborts the run.
**Source registry.** A `sources` table, seeded from `data/seed/sources.yaml`,
is the single source of truth for what gets ingested. Each row:
`id, name, base_url, connector, trust_tier, crawl_strategy, schedule, enabled,
config, discovered_by, added_at`. New rows can be added (by Scout or an admin)
without a code deploy as long as the `connector` already exists.
**Connectors** (one per source kind): `innovatiebudget` (list_detail),
`algoritmeregister` (api/paginated), `github_org` (GitHub API), `icai_labs`
(list_detail), `generic_html` (main-content extraction), `rss_news` (feeds),
`pdf_document` (download + text extract). Each implements
`discover_urls / fetch / parse`. `discover_urls` must never be hardcoded to a
fixed list — a new Innovatiebudget year or a new ICAI lab must be picked up
automatically.
**Trust tiers** drive conflict resolution and citation prominence:
`tier_1_primary` (government registries, official APIs, GitHub orgs, ministry
and `*.overheid.nl` sites, ICAI, AIC4NL), `tier_2_institutional` (koepels,
sector bodies, universities), `tier_3_media` (trade press — used for recency
and discovery, never as the sole source for a hard fact).
---
## 7. Knowledge graph — schema (the contract)
Build this first. It is identical in spirit to a well-formed GraphRAG schema;
do not deviate without a `# DESIGN-DECISION:`.
### 7.1 Node types
| Label               | Key properties                                               |
| ------------------- | ------------------------------------------------------------ |
| `Initiative`        | `name`, `aliases[]`, `kind` (project/programme/pilot/lab/hub/platform/register/framework), `description`, `status` (concept/pilot/in_use/scaled/completed/unknown), `themes[]`, `started_at`, `ended_at` |
| `Organisation`      | `name`, `aliases[]`, `org_type` (ministry/executive_agency/province/municipality/water_authority/ggd/safety_region/university/koepel/company/ngo), `government_layer` (rijk/provincie/gemeente/waterschap/regional/academic/private), `website` |
| `Person`            | `name`, `roles[]`, `current_org`                             |
| `Repository`        | `name`, `url`, `platform`, `primary_language`, `license`, `last_activity_at`, `stars`, `forks` |
| `Framework`         | `name`, `aliases[]`, `framework_type` (law/guideline/standard/assessment/policy), `issuer`, `current_version`, `url` |
| `Community`         | `name`, `purpose`, `owner_org`                               |
| `FundingInstrument` | `name`, `funder`, `typical_amount`, `cadence`                |
| `Theme`             | `name`, `slug`                                               |
| `Document`          | `document_id`, `url`, `title`, `source_id`, `trust_tier`, `published_at`, `observed_at` |
Controlled vocabularies live as enums in `extraction/schema.py`. The Extractor
must map to these enums; free-text values are rejected by the Critic.
### 7.2 Edge types
Directed. Every edge carries `source_document_ids[]`, `observed_at`,
`confidence` (0–1), optional `valid_from` / `valid_to`.
`RUN_BY` (Initiative→Organisation), `INITIATED_BY` (Initiative→Org/Person),
`PARTNER_IN` (Org/Person→Initiative), `FUNDED_BY` (Initiative→FundingInstrument),
`BUILDS_ON` (Initiative→Initiative), `SHARES_CODEBASE_WITH`
(Initiative→Repository), `HOSTS_REPO` (Organisation→Repository),
`WORKS_ON` (Person→Initiative), `EMPLOYED_BY` (Person→Organisation),
`PART_OF` (Organisation→Organisation), `MEMBER_OF` (Organisation→Community),
`GOVERNED_BY` (Initiative→Framework), `TAGGED` (→Theme),
`MENTIONS` (Document→any node, provenance), `RELATED_TO` (any→any, with a
`reason` string).
### 7.3 Provenance & temporality (mandatory)
- Every node and edge stores `source_document_ids[]`. A node without provenance
  is a bug the Critic must reject.
- Every node stores `first_observed_at` and `last_observed_at`.
- Facts are never hard-deleted. If a re-crawl no longer supports an edge, set
  `valid_to` and `status = stale` — the graph remains a historical asset.
- Conflicting property values are all kept as
  `{value, source_document_id, trust_tier, observed_at}`; the highest-tier
  most-recent value is exposed as primary, the rest stay queryable.
### 7.4 Entity resolution (deterministic first)
Before writing a node the Graph steward resolves it: (1) exact match on
normalised `name`/`alias`; (2) high-threshold fuzzy match; (3) for
`Organisation`, a canonical-name table seeded from `data/seed/canonical_orgs.yaml`
(e.g. "BZK", "Min. BZK", "Ministerie van Binnenlandse Zaken en
Koninkrijksrelaties" → one node). Steps 1–3 are deterministic and free. Only
genuine ambiguity escalates to an LLM call; truly uncertain merges go to the
dashboard merge queue. Resolution is deterministic and logged.
### 7.5 Community detection & summaries (incremental)
After each extraction batch, run Leiden community detection — but **only
recompute summaries for communities whose membership changed**, not the whole
graph (a cost control). Each `Community` summary is an LLM-generated narrative
of what binds the cluster, stored with provenance. These summaries power
"global" GraphRAG questions that vector search alone cannot answer.
---
## 8. Storage
- **Neo4j** — the knowledge graph (Section 7).
- **Qdrant** — chunk embeddings; payload includes `document_id`, `source_id`,
  `trust_tier`, `observed_at`, and the IDs of graph nodes the chunk mentions
  (so a vector hit can jump into the graph).
- **PostgreSQL** — `sources`, `documents`, `chunks`, `ingestion_runs`,
  `extraction_cache`, `cost_ledger`, `agent_runs`, `review_queue`,
  `merge_review`, `schema_proposals`, `journeys`, `chat_sessions`,
  `chat_messages`, `community_summaries`, `answer_cache`.
- **Object store** — raw document snapshots, keyed by
  `source_id + url + content_hash`, so re-extraction never needs a re-fetch.
**Graph writer** — `writer.py`, idempotent upserts via Cypher `MERGE` on stable
keys, never `CREATE`. Every write appends to `source_document_ids` and updates
`last_observed_at`. One transaction per document.
**The graph as a standalone exportable asset (capability 3).** Provide:
`GET /api/graph/export?format=graphml|json|cypher`, a CSV export per node and
edge type, a read-only allowlisted Cypher endpoint
(`POST /api/graph/query`, with a cost/row limit), and a weekly timestamped
full-graph snapshot written to the object store so the graph's evolution is
itself an asset.
---
## 9. Hooks & observability
Agent SDK hooks are the backbone of both governance and the dashboard.
- **`PreToolUse`** — (a) **budget gate**: check the cost ledger against
  per-run / per-day / per-agent caps; block-and-queue if exceeded (3.13).
  (b) **politeness gate**: enforce rate limits and robots on Web/GitHub MCP
  calls. (c) **safety gate**: refuse tool calls that would exfiltrate data or
  act on instructions found inside fetched content (treat fetched page content
  as untrusted data, never as instructions).
- **`PostToolUse`** — write telemetry: which agent, which tool, latency,
  success/failure, and — for LLM calls routed via the gateway — the cost-ledger
  row. This is what the dashboard reads.
- **`SessionStart`** — load relevant memory/context for the agent (e.g. the
  canonical-org table for the Graph steward).
Plus: structured JSON logs with a trace ID per run; OpenTelemetry traces;
`/health` and `/metrics` endpoints. The Watchdog (4.12) turns hook events into
health metrics and alerts.
---
## 10. Retrieval & reasoning (query plane)
### 10.1 The cheap path vs the expensive path
The Planner's Tier-A classifier routes every question:
- **Simple / local** ("who runs X?", "which repo holds Y?") → deterministic
  hybrid retrieval (10.2) + one Tier-B Synthesizer call. No multi-agent loop.
  Check the answer cache first.
- **Journey** → the Journey agent (Section 11).
- **Complex / global** ("what are the white spots in municipal AI?") → the
  Research agent's bounded loop, using community summaries for global questions.
### 10.2 Hybrid retrieval (deterministic)
Three retrievals in parallel, fused with Reciprocal Rank Fusion: vector search
over chunks (Qdrant, filtered by trust tier / recency when the query implies
it), BM25 keyword search (exact names, acronyms, IDs), and graph retrieval
(entity-link the query, traverse N hops, pull connected nodes + their
provenance documents). De-duplicate by `document_id`.
### 10.3 GraphRAG synthesis
Local mode for specific questions (entity + neighbourhood + supporting chunks);
global mode for broad questions (map over relevant community summaries, then
reduce). Every answer cites every fact with URL, trust tier, and `observed_at`;
flags conflicts; never asserts an uncited fact; offers graph-anchored
follow-ups.
---
## 11. Journeys & open research (capability 4)
### 11.1 Journeys
A journey is a declarative, multi-step flow stored as data (JSON in the
`journeys` table) so journeys can be added or edited without a deploy. Step
types: `user_input`, `graph_query`, `hybrid_retrieval`, `rank`, `synthesis`,
`suggest_followups`, `branch`. The Journey agent executes steps in order,
pausing at `user_input`. Ship the runner plus 2–3 example journeys (e.g.
"Wie heeft dit al gebouwd?", "Leg dit landschap uit voor een nieuwkomer",
"Wat zijn de regels voor mijn AI-project?"); the product owner defines the rest
later.
Example definition:
```json
{
  "id": "find-who-built-x",
  "title": "Wie heeft dit al gebouwd?",
  "steps": [
    { "id": "topic",   "type": "user_input",
      "prompt": "Welk type oplossing zoek je?" },
    { "id": "find",    "type": "graph_query", "uses": "topic" },
    { "id": "rank",    "type": "rank", "by": ["status","trust_tier","recency"] },
    { "id": "present", "type": "synthesis" },
    { "id": "next",    "type": "suggest_followups" }
  ]
}
```
### 11.2 Open research
The Research agent (4.11): decompose → retrieve per sub-question → identify
gaps → optionally ingest a missing source on demand → synthesise a structured,
cited brief, exportable to Markdown/PDF. The loop is hard-capped (sub-questions,
tool calls) and the budget hook applies; progress streams to the UI.
---
## 12. Interface (capability 5) + management dashboard
Next.js 14 App Router, TypeScript strict, responsive, Dutch UI copy,
light/dark mode. The app has two surfaces: the **explorer** (end users) and the
**management dashboard** (operators).
### 12.1 Global shell
Left sidebar: Chat · Verkennen (graph) · Zoeken · Journeys · Bronnen ·
Dashboard (operators). Command palette (`Cmd/Ctrl-K`). Global search in the top
bar.
### 12.2 Chat / GraphRAG view
Streaming answers. Citations are first-class: every cited claim has an inline
marker; hover shows source title, URL, trust tier, `observed_at`; a side panel
lists all sources. Below each answer, "entiteiten in dit antwoord" chips link
into the graph explorer. Conflict callouts are rendered as distinct notices.
Graph-anchored follow-up suggestions.
### 12.3 Structured search
Faceted by `government_layer`, `org_type`, `status`, `theme`, `kind`, year,
`trust_tier`. Results as typed cards (initiative / organisation / person / repo
/ framework), each linking to its graph node and its sources.
### 12.4 Graph explorer (the centrepiece)
Overview canvas with Sigma.js + graphology (WebGL, smooth at 5.000+ nodes,
clustered by community); detail view with Cytoscape.js for an N-hop
neighbourhood. Node colour = type, size = centrality, edge style = type, legend
always visible. Click a node → side panel with all properties, sources, and an
"vraag de chatbot over dit knooppunt" button. Filters by type, government
layer, theme, time range. A shortest-path tool between two nodes. A time
scrubber that replays graph growth via `first_observed_at`. A list-view
fallback of any subgraph for accessibility.
### 12.5 Journeys view
Gallery of journey cards; running one renders as a guided stepwise flow with
progress; results link into graph + sources.
### 12.6 Learning & synthesis
Save/collections (bookmark nodes, answers, searches into named collections);
export any answer/brief/collection to Markdown and PDF with full citations and
a "geraadpleegd op" date; glossary mode (hover an acronym → definition from a
`Framework`/`Organisation` node); a "leg uit voor een nieuwkomer" toggle that
reframes any answer at onboarding level; a freshness indicator on every entity
showing when it was last confirmed by a crawl.
### 12.7 UX principles
Never a dead end (every view offers a next step). Trust is visible (tier + date
next to every fact). Progressive disclosure. Fast (search < 300 ms perceived;
stream long answers). Accessible (keyboard navigable, WCAG AA, screen-reader
labels + list fallback on the graph).
### 12.8 Management dashboard (operators)
A dedicated `/dashboard` surface. Its job is to make the system's health, the
graph's health, **and the cost** controllable. Panels:
1. **Overview** — status cards: sources active (e.g. 23/25), nodes, edges, cost
   today, groundedness eval score, last sync time. A green/amber/red system
   health indicator.
2. **Cost** — the most important operator panel:
   - Spend today / this week / this month vs budget, from the `cost_ledger`.
   - Spend broken down **per agent** and **per model tier** (stacked).
   - **Change-detection skip rate** and **cache hit rates** (extraction cache,
     prompt cache, embedding cache, answer cache) — these are the levers; show
     them as headline numbers with trend.
   - Batch-vs-sync token split.
   - Budget caps (per-run / per-day / per-agent) — editable here.
   - A **what-if estimator** (3.15): sliders for corpus size, change rate,
     crawl cadence, Critic sample rate → projected monthly cost.
   - Alerts when a cap is approached or the cost trend breaks out.
3. **Agent activity** — live and recent agent runs: which agent, what it is
   doing, status (bezig / klaar / aandacht), duration, token spend per run.
   Failed or flagged runs are clickable for the trace.
4. **Knowledge graph health** — node/edge counts over time, growth rate, orphan
   nodes (no provenance — should be zero), staleness heatmap (nodes not
   confirmed recently), conflict count.
5. **Source registry & freshness** — every source: connector, trust tier, last
   crawl, status, consecutive-error streak, change rate. Controls to pause a
   source, force a re-crawl, edit its schedule.
6. **Review queues** (human-in-the-loop) — three tabs:
   - **New sources** — Scout's proposals; approve (sets `enabled: true`) or
     reject.
   - **Merges** — Graph steward's uncertain entity merges; confirm or split.
   - **Schema proposals** — Graph steward's schema-evolution drafts; approving
     one triggers a budgeted, off-peak Batch re-extraction (3.8) with a
     progress bar.
7. **Evaluation** — extraction precision/recall, retrieval recall@k, answer
   groundedness trend (Section 13), with a fail line.
8. **Usage analytics** — top questions, journeys used, dead-end questions
   (no good answer) — feeds journey design.
9. **Manual controls** — trigger a crawl, run the Scout now, roll back to a
   graph snapshot, re-run a failed agent run, flush a cache.
---
## 13. API surface
FastAPI; SSE for streaming. Fact-bearing responses always carry citations.
```
# Chat & retrieval
POST /api/chat                  stream a GraphRAG answer (SSE)
POST /api/research              start an open-research run (SSE progress)
GET  /api/search?q=             hybrid structured search
# Journeys
GET  /api/journeys              list definitions
POST /api/journeys/{id}/run     start/continue a run
GET  /api/journeys/{id}         get one definition
# Graph
GET  /api/graph/node/{id}       node + neighbourhood
GET  /api/graph/subgraph?...    filtered subgraph
GET  /api/graph/export          export (graphml|json|cypher|csv)
POST /api/graph/query           allowlisted read-only Cypher
# Entities
GET  /api/initiatives | /organisations | /people | /repositories | /frameworks
# Management dashboard
GET  /api/admin/overview        status cards
GET  /api/admin/cost            ledger rollups, cache rates, skip rate
POST /api/admin/cost/estimate   what-if estimator
GET/PUT /api/admin/budgets      budget caps
GET  /api/admin/agent-runs      agent run history + traces
GET  /api/admin/graph-health    counts, orphans, staleness, conflicts
GET  /api/admin/sources         registry + freshness
POST /api/admin/sources         add a source
POST /api/admin/sources/{id}/crawl   force a crawl
GET  /api/admin/review-queue    discovery / merge / schema queues
POST /api/admin/review/{id}     approve/reject
GET  /api/admin/evals           eval scores
GET  /api/admin/usage           usage analytics
POST /api/admin/snapshot/rollback    roll back graph snapshot
GET  /health   GET /metrics
```
---
## 14. Build plan — phased
Work in order. Stop after each phase, run its acceptance checks, summarise.
**Phase 0 — Scaffolding.** Monorepo, docker-compose (Neo4j, Qdrant, Postgres,
Redis, MinIO), `.env.example`, FastAPI + Next.js skeletons, CI (lint, type-check,
tests).
*Accept:* `docker-compose up` brings everything up; `/health` green.
**Phase 1 — Cost gateway & schema.** `cost/gateway.py`, `cost_ledger`,
`cost/budget.py`, the pricing table in config; the Section 7 schema in
`extraction/schema.py`; `GraphStore` + Neo4j impl; idempotent `writer.py`;
Postgres models. Lint check: nothing imports the Anthropic client except the
gateway.
*Accept:* every node/edge type can be created/merged/queried; a stub LLM call
writes a correct `cost_ledger` row; budget caps block-and-queue correctly.
**Phase 2 — Deterministic spine.** Source registry + seed YAML; connectors
(`innovatiebudget`, `algoritmeregister`, `github_org`, `icai_labs`); pipeline
steps 1–9; change detection; embedding with cache; scheduler.
*Accept:* a scheduled run ingests the four sources with zero LLM calls;
re-running an unchanged source produces a ~100% skip rate and zero new cost.
**Phase 3 — MCP servers.** Graph, Vector, Web, GitHub, SQL FastMCP servers with
scoped tool allowlists.
*Accept:* each server's tools callable; write tools reject callers without the
allowlist.
**Phase 4 — Knowledge-plane agents.** Extractor (Batch API, prompt caching,
extraction cache), selective Critic, Graph steward (deterministic resolution +
schema proposals), incremental community detection. Hooks for budget +
telemetry.
*Accept:* a golden set of 20 known initiatives appears correctly in the graph;
extraction evals pass; every node has provenance; re-running ingestion on
unchanged data produces zero LLM calls (cache + change detection verified);
budget hook caps a run correctly.
**Phase 5 — Query-plane agents.** Planner (Tier-A classifier + decomposition),
deterministic hybrid retrieval, retrieval squad, Synthesizer, answer cache;
chat API with streaming citations.
*Accept:* retrieval evals pass recall@k; simple questions take the cheap path
(verified in the ledger); answers carry correct citations and never assert
uncited facts.
**Phase 6 — Frontend explorer.** Global shell, chat with citations + entity
chips, structured search, graph explorer (Sigma + Cytoscape, filters, path
tool, time scrubber).
*Accept:* ask → cited streamed answer → click entity → graph; smooth at 5.000+
nodes.
**Phase 7 — Journeys, research, Scout.** Journey runner + 2–3 example journeys;
Research agent (bounded loop); Scout + discovery; export to Markdown/PDF;
collections.
*Accept:* example journeys run end-to-end; Scout proposes sources into the
review queue within its candidate cap; a research brief exports with citations.
**Phase 8 — Management dashboard.** All panels in 12.8, the what-if estimator,
graph export endpoints + weekly snapshot, alerting.
*Accept:* dashboard shows live cost broken down per agent and per tier; skip
rate and cache hit rates are visible; budget caps editable and enforced; review
queues approve/reject correctly; alerts fire on simulated cap breach and source
failure.
---
## 15. Evaluation
Pytest-based eval harness from day one. **Ingestion evals**: 20-initiative
golden set appears with correct type/status/relations. **Extraction evals**:
labelled snippets → expected entities/relations; precision/recall with a CI
fail threshold. **Retrieval evals**: question set with known-correct documents;
recall@k + citation correctness. **Answer evals**: LLM-as-judge rubric scoring
groundedness (no uncited claims), correctness, completeness. **Graph integrity
checks** after every ingestion: no node without provenance, no edge with null
`confidence`, controlled-vocabulary values only, no orphan `Document` nodes.
**Cost regression check**: a re-ingestion of unchanged data must produce zero
LLM calls — fail CI if it does not.
---
## 16. Definition of done
- `docker-compose up` runs the entire stack from clean.
- A scheduled ingestion populates the graph from all seed sources; re-running
  unchanged sources costs zero LLM tokens (change detection + caches verified).
- The Scout proposes new sources into a review queue weekly, within its cap.
- The knowledge graph is queryable directly and exportable in GraphML, JSON,
  Cypher, and CSV.
- Chat answers are streamed, grounded, cited with tier + date; uncited facts
  never appear; simple questions take the cheap path.
- Graph explorer, structured search, journeys, and open research all work and
  cross-link.
- The management dashboard shows live cost per agent and per tier, skip and
  cache rates, agent activity, graph health, source freshness, review queues,
  evals, and the what-if estimator; budget caps are editable and enforced.
- Every LLM call goes through `cost/gateway.py` and lands in `cost_ledger`.
- All evals pass in CI, including the zero-cost re-ingestion regression check;
  `ingestion/`, `agents/`, `graph/`, `cost/` ≥70% coverage.
- `README.md` documents setup, the source registry, how to add a connector, an
  agent, a journey, and an MCP server, the graph schema, and the cost model.
---
## 17. Appendix — seed knowledge & cost reality check
The project knowledge contains a research report on the Dutch government
digital-innovation landscape. Use it to seed the canonical-organisation table
(BZK, ICTU, VNG, AIC4NL, ICAI and alias forms), the `Theme` vocabulary, the
20-initiative golden set, and `data/seed/sources.yaml`. Treat the report as
tier-2 seed knowledge: it bootstraps the graph, but every fact must be
re-confirmed by a tier-1 crawl and carry its own provenance.
**Cost reality check for the operator.** The dominant cost is one-time:
extracting the initial corpus. Steady state is cheap because (a) the
deterministic spine has no LLM cost, (b) weekly re-crawls re-extract only the
5–15% of documents that actually changed, (c) the Extractor's static prompt is
prompt-cached, (d) backlogs run on the Batch API, (e) the Critic samples rather
than reviews everything, and (f) most user questions take the cheap retrieval
path. The dashboard's what-if estimator (3.15) lets the operator see the
monthly figure before committing, using a pricing table they keep current from
`https://docs.claude.com`. If steady-state cost is ever surprising, the first
three things to check are the change-detection skip rate, the prompt-cache hit
rate, and the Critic sample rate — in that order.
