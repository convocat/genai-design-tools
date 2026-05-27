# SPEC — GovInnovatie GraphRAG Explorer
> A GraphRAG-powered chatbot and interactive explorer for the digital innovation
> landscape of the Dutch government. This document is the build specification.
> It is written to be handed directly to Claude Code.

> **This file is FROZEN as the contract.** Do not edit it. All deviations go to
> `.claude/decisions.md` instead. Frozen on 2026-05-27.

---
## 0. How to use this document (instructions for Claude Code)
You are building the system described below. Work in phases (see Section 12).
After each phase, stop, run the phase's acceptance checks, and summarize what was
built before continuing. Do not skip the knowledge-graph schema (Section 5) — it
is the contract every other component depends on.
Ground rules:
- **Language of the product:** the corpus and UI copy are Dutch; code, comments,
  identifiers, and commit messages are English. LLM prompts that process Dutch
  source text must instruct the model to keep entity names in original Dutch.
- **Determinism first:** ingestion and graph-building must be re-runnable and
  idempotent. Running ingestion twice on unchanged sources must not create
  duplicate nodes or edges.
- **Everything is typed.** Python: full type hints + Pydantic models. TypeScript:
  strict mode, no `any`.
- **No secret in the repo.** All credentials via environment variables and a
  `.env` file that is git-ignored. Provide `.env.example`.
- **Test as you go.** Every connector, every extractor, and every retrieval
  function gets unit tests. Target ≥70% coverage on the `ingestion/` and
  `graph/` packages.
- When a design decision is ambiguous and not specified here, choose the simpler
  option, leave a `# DESIGN-DECISION:` comment explaining the choice, and keep
  moving.
---
## 1. Product summary
### 1.1 What it is
An application that lets a user — typically an external consultant or civil
servant who does not know the Dutch government innovation landscape — explore
which digital innovation initiatives exist, how they relate, who runs them,
where the code and rules live, and what was learned. It does this through:
1. A **chat interface** backed by GraphRAG (retrieval that combines vector
   search with knowledge-graph traversal).
2. An **interactive graph explorer** (visual, navigable knowledge graph).
3. A **structured search** experience over initiatives, organisations, people,
   repositories, frameworks, communities, and funding instruments.
4. **Guided journeys** — predefined, multi-step flows (defined later) for
   recurring questions.
5. **Open research mode** — free-form exploration and multi-source synthesis
   with citations and export.
### 1.2 Five required capabilities (from the brief)
| #    | Capability                                                  | Where it is specified |
| ---- | ----------------------------------------------------------- | --------------------- |
| 1    | Ingest source content on a regular schedule                 | Section 3, 4          |
| 2    | Discover new sources and update automatically               | Section 4.4           |
| 3    | Build a knowledge graph usable standalone and for retrieval | Section 5, 6          |
| 4    | Offer fixed journeys + open research/exploration            | Section 8             |
| 5    | Best-in-class UX for search, retrieval, learning, synthesis | Section 9             |
### 1.3 Non-goals (v1)
- No write-back to government systems.
- No authentication beyond a single shared deployment (add SSO later).
- No multi-tenant support.
- No mobile-native app (responsive web is enough).
---
## 2. Architecture overview
Five layers plus a cross-cutting orchestration/observability layer.
```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5 — INTERFACE                                          │
│  Next.js app: chat · search · graph explorer · journeys ·     │
│  export                                                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 4 — RETRIEVAL & REASONING                              │
│  Hybrid search · graph traversal · GraphRAG synthesis ·       │
│  journey runner · agentic research loop                       │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 — KNOWLEDGE GRAPH & STORAGE                          │
│  Graph DB · vector index · document store · object store      │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 — INGESTION & ENRICHMENT                             │
│  Connectors · scheduler · discovery agent · normaliser ·      │
│  chunker · entity/relation extractor · graph writer           │
├─────────────────────────────────────────────────────────────┤
│  Layer 1 — SOURCES                                            │
│  Innovatiebudget · Algoritmeregister · GitHub · ICAI ·        │
│  AIC4NL · news · sitemaps                                     │
└─────────────────────────────────────────────────────────────┘
        ↕  Orchestration · scheduling · observability · evals
```
### 2.1 Technology choices
These are the defaults. If you (Claude Code) have a strong, well-justified
reason to deviate, leave a `# DESIGN-DECISION:` comment, but prefer this stack:
| Concern                        | Choice                                                       | Notes                                                        |
| ------------------------------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| Language (backend)             | Python 3.12                                                  | Ingestion, graph, retrieval API                              |
| Language (frontend)            | TypeScript + Next.js 14 (App Router)                         | UI                                                           |
| Graph database                 | **Neo4j 5** (Community)                                      | Mature, Cypher, good viz tooling. Abstract behind a `GraphStore` interface so it can be swapped. |
| Vector store                   | **Qdrant**                                                   | Standalone, good filtering. Alternatively pgvector if you want one fewer service. |
| Document/metadata store        | **PostgreSQL 16**                                            | Raw documents, chunks, ingestion runs, source registry, journey definitions, chat history |
| Object store                   | Local volume in dev, S3-compatible (MinIO) in prod           | Raw HTML/PDF snapshots                                       |
| Task queue / scheduler         | **Celery + Redis**, beat for cron                            | Scheduled ingestion + async jobs                             |
| LLM provider                   | Anthropic API (Claude)                                       | Extraction, synthesis, chat. Model IDs in config, not hardcoded. |
| Embeddings                     | A multilingual embedding model that handles Dutch well       | Configurable; must support Dutch.                            |
| API framework                  | FastAPI                                                      | Backend HTTP API                                             |
| Frontend graph viz             | **Sigma.js + graphology** (large graphs) and **Cytoscape.js** (detail views) | See 9.4                                                      |
| Containerisation               | Docker + docker-compose                                      | One command to run the whole stack                           |
| Orchestration of ingestion DAG | Celery canvas (chains/groups)                                | Keep it simple; no Airflow in v1                             |
| Observability                  | Structured logging (JSON) + OpenTelemetry traces + a `/health` and `/metrics` endpoint |                                                              |
| Eval harness                   | Custom, pytest-based, see Section 11                         |                                                              |
### 2.2 Repository layout (monorepo)
```
govinnovatie-explorer/
├── docker-compose.yml
├── .env.example
├── README.md
├── SPEC.md                      ← this file
├── backend/
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py              ← FastAPI entrypoint
│   │   ├── config.py            ← Pydantic Settings
│   │   ├── api/                 ← HTTP routes
│   │   ├── ingestion/
│   │   │   ├── connectors/      ← one module per source type
│   │   │   ├── scheduler.py
│   │   │   ├── discovery.py     ← new-source discovery agent
│   │   │   ├── normalise.py
│   │   │   ├── chunk.py
│   │   │   └── pipeline.py      ← the ingestion DAG
│   │   ├── extraction/
│   │   │   ├── schema.py        ← entity/relation type definitions
│   │   │   ├── extractor.py     ← LLM-based entity/relation extraction
│   │   │   └── resolver.py      ← entity resolution / dedup
│   │   ├── graph/
│   │   │   ├── store.py         ← GraphStore interface + Neo4j impl
│   │   │   ├── writer.py        ← idempotent upserts
│   │   │   ├── community.py     ← community detection + summaries
│   │   │   └── export.py        ← graph export (see 6.4)
│   │   ├── retrieval/
│   │   │   ├── hybrid.py        ← vector + keyword + graph
│   │   │   ├── graphrag.py      ← GraphRAG synthesis
│   │   │   ├── journeys.py      ← journey runner
│   │   │   └── research.py      ← open agentic research loop
│   │   ├── models/              ← Pydantic + SQLAlchemy models
│   │   └── tasks/               ← Celery tasks
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── app/                     ← Next.js App Router
│   ├── components/
│   ├── lib/
│   └── tests/
└── data/
    └── seed/                    ← seed source registry (Section 4.1)
```
---
## 3. Layer 1 — Sources
The corpus is the Dutch government digital-innovation landscape. Sources fall
into structured, semi-structured, and unstructured categories. The system must
treat each source as a registry entry (Section 4.1) so new ones can be added
without code changes where possible.
### 3.1 Seed sources (must be supported at launch)
**Structured / API-like (highest priority — best signal):**
| Source                            | URL                                                          | Type                             | What it yields                                               |
| --------------------------------- | ------------------------------------------------------------ | -------------------------------- | ------------------------------------------------------------ |
| Innovatiebudget Digitale Overheid | `digitaleoverheid.nl/.../innovatiebudget/` + per-year archives `/jaar-toekenning/{year}/` | HTML list + detail pages         | ~110 funded projects 2019–2025 with initiators, description, status, lessons |
| Algoritmeregister                 | `algoritmes.overheid.nl`                                     | Has open data / structured pages | ~1.400 algorithms, ~305 organisations                        |
| MinBZK GitHub                     | `github.com/orgs/MinBZK/repositories`                        | GitHub REST/GraphQL API          | 130+ repositories, descriptions, languages, activity         |
| Gemeente Amsterdam GitHub         | `github.com/Amsterdam`                                       | GitHub API                       | Municipal open-source repos                                  |
| code.overheid.nl                  | `code.overheid.nl`                                           | HTML / Forgejo                   | Cross-government code platform index                         |
| developer.overheid.nl             | `developer.overheid.nl`                                      | HTML / API                       | Standards, APIs, repositories                                |
| ICAI labs                         | `icai.ai/labs/`                                              | HTML list + detail               | 50+ AI labs, partners, scientific directors                  |
| AIC4NL                            | `aic4nl.nl`                                                  | HTML                             | AI coalition, 7 regional hubs, instruments                   |
**Semi-structured (institutional pages):**
- `digitaleoverheid.nl` (communities, organisations, news sections)
- `rijksinnovatiecommunity.nl`
- `ggdghor.nl`, `hetwaterschapshuis.nl`, `nipv.nl`
- University AI-lab pages (UU, UvA, TU Delft, Leiden, Radboud)
- `vng.nl` (Common Ground, Gem)
**Unstructured (news / trade media — lower trust, used for freshness):**
- `ibestuur.nl`, `binnenlandsbestuur.nl`, `computable.nl`, `gemeente.nu`
**Government documents:**
- `open.overheid.nl` and `tweedekamer.nl` (Kamerstukken, frameworks) — PDF.
### 3.2 Source trust tiers
Every source carries a `trust_tier` used downstream for conflict resolution and
citation prominence:
- `tier_1_primary` — government registries, official APIs, GitHub orgs,
  institutional sites (`*.overheid.nl`, ministry sites, ICAI, AIC4NL).
- `tier_2_institutional` — koepels and sector bodies (VNG, GGD GHOR, NIPV,
  Het Waterschapshuis, universities).
- `tier_3_media` — trade press. Used for recency signals and to *discover*
  initiatives, never as the sole source for a hard fact.
When facts conflict, prefer the higher tier and the more recent
`observed_at` (Section 5).
---
## 4. Layer 2 — Ingestion & enrichment
### 4.1 Source registry
A database table `sources` is the single source of truth for what gets
ingested. Seeded from `data/seed/sources.yaml`. Schema:
```yaml
# data/seed/sources.yaml — one entry per source
- id: innovatiebudget
  name: "Innovatiebudget Digitale Overheid"
  base_url: "https://www.digitaleoverheid.nl/overzicht-van-alle-onderwerpen/innovatie/innovatiebudget/"
  connector: "innovatiebudget"      # which connector module handles it
  trust_tier: "tier_1_primary"
  crawl_strategy: "list_detail"     # list_detail | api | sitemap | rss | single_page
  schedule: "weekly"                # daily | weekly | monthly
  enabled: true
  config:                           # connector-specific
    year_archive_pattern: "https://www.digitaleoverheid.nl/jaar-toekenning/{year}/"
    years: [2019, 2020, 2021, 2023, 2024, 2025, 2026]
  discovered_by: "seed"             # seed | discovery_agent
  added_at: "2026-05-27"
```
The registry must support adding a row (via discovery agent or admin UI)
without a code deploy, as long as the `connector` already exists.
### 4.2 Connectors
A connector knows how to fetch and parse one *kind* of source. Implement these:
| Connector           | Strategy              | Notes                                                        |
| ------------------- | --------------------- | ------------------------------------------------------------ |
| `innovatiebudget`   | list_detail           | Crawl year archives → project detail pages. Extract: project name, initiators, description, status, theme, lessons. |
| `algoritmeregister` | api                   | Use the register's open-data endpoint if available; else paginate HTML. One node per algorithm + per organisation. |
| `github_org`        | api                   | GitHub GraphQL API. Per repo: name, description, topics, primary language, stars/forks, last commit, README excerpt, license. |
| `icai_labs`         | list_detail           | Lab list → lab detail. Extract partners, scientific directors, domain, period. |
| `generic_html`      | sitemap / single_page | Trafilatura-style main-content extraction for institutional pages. |
| `rss_news`          | rss                   | For trade media that expose feeds.                           |
| `pdf_document`      | single_page           | Download + extract text from government PDFs.                |
**Connector contract** — every connector implements:
```python
class Connector(Protocol):
    source_id: str
    def discover_urls(self, source: SourceConfig) -> list[CrawlTarget]:
        """Return the set of URLs/records to fetch for this run."""
    def fetch(self, target: CrawlTarget) -> RawDocument:
        """Fetch one target. Must be polite: respect robots.txt,
        rate-limit, set a descriptive User-Agent, retry with backoff."""
    def parse(self, raw: RawDocument) -> list[ParsedRecord]:
        """Turn raw content into normalised ParsedRecords."""
```
**Politeness requirements (non-negotiable):**
- Respect `robots.txt`.
- Descriptive `User-Agent` identifying the project + a contact URL.
- Per-domain rate limit (default: 1 request / 2 seconds; configurable).
- Exponential backoff on 429/5xx; max 5 retries.
- Conditional requests (`ETag` / `If-Modified-Since`) where supported.
- Store a raw snapshot of every fetched document in the object store, keyed by
  `source_id + url + content_hash`, so re-extraction never needs a re-fetch.
### 4.3 Ingestion pipeline (the DAG)
Per source, per scheduled run:
```
1. RESOLVE TARGETS   connector.discover_urls() → list of CrawlTarget
2. FETCH             connector.fetch() each target (parallel, rate-limited)
                     skip if content_hash unchanged since last run
3. SNAPSHOT          store raw doc in object store
4. PARSE             connector.parse() → ParsedRecord[]
5. NORMALISE         clean text, strip boilerplate, detect language,
                     resolve dates to ISO, canonicalise org names
6. CHUNK             split into retrieval chunks (see 4.5)
7. EMBED             embed each chunk → vector store
8. EXTRACT           LLM entity/relation extraction (see Section 5)
9. RESOLVE           entity resolution against existing graph (see 5.4)
10. WRITE GRAPH      idempotent upsert of nodes + edges (see 6.2)
11. RECORD RUN       write IngestionRun row: counts, errors, duration
```
Each step is a Celery task; the per-source run is a Celery chain. Steps 2 and 8
fan out with a Celery group. A failure in one target must not abort the whole
run — collect errors, continue, report at the end.
**Idempotency:** every document has a stable `document_id =
hash(source_id + canonical_url)`. Re-ingesting updates in place. Every node and
edge carries `source_document_ids` (provenance) so a re-run reconciles rather
than duplicates.
**Change detection:** compare `content_hash`. If unchanged, skip steps 4–10.
If changed, re-run and *diff* the extracted entities so the graph reflects
removals, not just additions.
### 4.4 Discovery agent (requirement 2 — find new sources automatically)
A scheduled job (`discovery.py`, runs weekly) that grows the corpus:
**A. New records within known sources** — connectors already re-crawl list
pages, so a new Innovatiebudget year or a new ICAI lab is picked up
automatically. No agent needed; just make sure `discover_urls()` is not
hardcoded to a fixed list.
**B. New sources** — the discovery agent:
1. Takes a set of *seed signals*: outbound links found in already-ingested
   tier-1/2 documents, plus a small set of curated search queries (e.g.
   "gemeente AI innovatie project", "datalab provincie", "ICAI lab overheid").
2. Runs web searches and collects candidate domains/URLs.
3. For each candidate, an LLM classifier scores it against an inclusion rubric:
   *Is this a Dutch public-sector digital-innovation initiative, organisation,
   community, repository, or framework?* Output: `relevant` boolean +
   `confidence` + `proposed_connector` + `proposed_trust_tier` + rationale.
4. Candidates with `confidence ≥ threshold` and a connector that already exists
   are auto-added to the `sources` table as `enabled: false`,
   `discovered_by: discovery_agent`.
5. All candidates (including auto-added) land in an **admin review queue**.
   A human flips `enabled: true` to activate. Auto-enable is allowed only for
   `github_org` and `generic_html` connectors on `*.overheid.nl` domains —
   everything else needs review. This keeps the corpus from drifting.
The discovery agent must be conservative: precision over recall. It is better
to miss a source than to pollute the graph. Log every decision.
### 4.5 Chunking
- Chunk on semantic boundaries (headings, list items, project records), not
  fixed token windows.
- For structured records (one Innovatiebudget project, one algorithm, one
  repo) the record *is* the chunk — do not split it.
- Target 200–500 tokens per chunk for prose; keep structured records whole even
  if larger.
- Every chunk stores: `document_id`, `source_id`, `url`, `chunk_index`,
  `text`, `heading_path`, `observed_at`, `trust_tier`.
---
## 5. Knowledge graph — schema (the contract)
This schema is the heart of the system. Build it first; do not deviate without
recording a `# DESIGN-DECISION:`.
### 5.1 Node types (entities)
| Label               | Description                                                  | Key properties                                               |
| ------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| `Initiative`        | A project, programme, pilot, lab, hub, register, or platform | `name`, `aliases[]`, `kind` (project/programme/pilot/lab/hub/platform/register/framework), `description`, `status` (concept/pilot/in_use/scaled/completed/unknown), `themes[]`, `started_at`, `ended_at` |
| `Organisation`      | Any public body or partner                                   | `name`, `aliases[]`, `org_type` (ministry/executive_agency/province/municipality/water_authority/ggd/safety_region/university/koepel/company/ngo), `government_layer` (rijk/provincie/gemeente/waterschap/regional/academic/private), `website` |
| `Person`            | A named individual with a public role                        | `name`, `roles[]`, `current_org`                             |
| `Repository`        | A code repository                                            | `name`, `url`, `platform` (github/forgejo/gitlab), `primary_language`, `license`, `last_activity_at`, `stars`, `forks` |
| `Framework`         | A law, guideline, standard, or assessment                    | `name`, `aliases[]`, `framework_type` (law/guideline/standard/assessment/policy), `issuer`, `current_version`, `url` |
| `Community`         | A community of practice, network, or platform                | `name`, `purpose`, `owner_org`                               |
| `FundingInstrument` | A budget, subsidy, or fund                                   | `name`, `funder`, `typical_amount`, `cadence`                |
| `Theme`             | A controlled-vocabulary topic tag                            | `name`, `slug`                                               |
| `Document`          | A source document (provenance anchor)                        | `document_id`, `url`, `title`, `source_id`, `trust_tier`, `published_at`, `observed_at` |
Controlled vocabularies (`kind`, `status`, `org_type`, `government_layer`,
`framework_type`, `Theme`) live in `extraction/schema.py` as enums. The
extractor must map to these enums — free-text values are rejected.
### 5.2 Edge types (relations)
Directed edges. Every edge carries `source_document_ids[]`, `observed_at`,
`confidence` (0–1 from the extractor), and optional `valid_from` / `valid_to`.
| Edge                   | From → To                        | Meaning                                             |
| ---------------------- | -------------------------------- | --------------------------------------------------- |
| `RUN_BY`               | Initiative → Organisation        | Organisation runs / owns the initiative             |
| `INITIATED_BY`         | Initiative → Organisation/Person | Originator                                          |
| `PARTNER_IN`           | Organisation/Person → Initiative | Is a partner                                        |
| `FUNDED_BY`            | Initiative → FundingInstrument   | Funding relationship                                |
| `BUILDS_ON`            | Initiative → Initiative          | Successor / builds on a predecessor                 |
| `SHARES_CODEBASE_WITH` | Initiative → Repository          | Has / shares a repository                           |
| `HOSTS_REPO`           | Organisation → Repository        | Owns the repo org                                   |
| `WORKS_ON`             | Person → Initiative              | Named contributor/contact                           |
| `EMPLOYED_BY`          | Person → Organisation            | Affiliation                                         |
| `PART_OF`              | Organisation → Organisation      | E.g. a directorate within a ministry                |
| `MEMBER_OF`            | Organisation → Community         | Participates in a community                         |
| `GOVERNED_BY`          | Initiative → Framework           | Subject to a framework                              |
| `TAGGED`               | Initiative/Organisation → Theme  | Topic tagging                                       |
| `MENTIONS`             | Document → any node              | Provenance: this document is evidence for this node |
| `RELATED_TO`           | any → any                        | Weak/uncertain link; carries a `reason` string      |
### 5.3 Provenance & temporality (mandatory)
- **Every** node and edge stores `source_document_ids[]`. A node with no
  provenance is a bug.
- Every node stores `first_observed_at` and `last_observed_at`.
- Facts are never hard-deleted. If a re-crawl no longer supports an edge, mark
  it `valid_to = <run date>` and `status = stale` rather than deleting it. This
  preserves the graph as a historical asset.
- Conflicting property values: keep all, store as
  `{value, source_document_id, trust_tier, observed_at}`; expose the
  highest-tier most-recent value as the "primary" but keep the rest queryable.
### 5.4 Entity resolution
Before writing a node, resolve it against the existing graph:
1. Exact match on normalised `name` or any `alias`.
2. Fuzzy match (normalised string similarity) above a high threshold →
   candidate merge.
3. For `Organisation`, maintain a canonical-name lookup table seeded from the
   research report (e.g. "BZK", "Min. BZK", "Ministerie van Binnenlandse Zaken
   en Koninkrijksrelaties" → one node).
4. Ambiguous matches go to a `merge_review` queue, not auto-merged.
5. Resolution must be deterministic and logged.
Seed the canonical-org table and the `Theme` vocabulary from the research
report already in the project knowledge.
### 5.5 Community detection & summaries (GraphRAG core)
After each graph update:
1. Run a community-detection algorithm (Leiden) over the graph.
2. For each community, generate an LLM **community summary**: what binds these
   nodes, the key initiatives/organisations, the narrative.
3. Store summaries as properties on a `Community`-like meta-node (or a separate
   `community_summaries` table) with provenance.
4. These summaries power "global" GraphRAG questions ("what are the main
   clusters of activity?") that vector search alone cannot answer.
---
## 6. Layer 3 — Storage
### 6.1 Stores
- **Neo4j** — the knowledge graph (nodes + edges from Section 5).
- **Qdrant** — chunk embeddings; payload includes `document_id`, `source_id`,
  `trust_tier`, `observed_at`, and the IDs of any graph nodes the chunk
  mentions (so vector hits can jump into the graph).
- **PostgreSQL** — `sources`, `documents`, `chunks`, `ingestion_runs`,
  `review_queue`, `journeys`, `chat_sessions`, `chat_messages`,
  `community_summaries`, `merge_review`.
- **Object store** — raw document snapshots.
### 6.2 Graph writer
A single `writer.py` module with idempotent upserts. Cypher `MERGE` on stable
keys, never `CREATE`. Every write appends to `source_document_ids` and updates
`last_observed_at`. Wrap each document's writes in one transaction.
### 6.3 GraphStore interface
All graph access goes through a `GraphStore` Protocol so Neo4j can be swapped.
No raw Cypher outside `graph/`.
### 6.4 Graph as a standalone exportable asset (requirement 3)
The graph must be usable independently of the chatbot. Provide:
- `GET /api/graph/export?format=graphml` — full graph as GraphML.
- `GET /api/graph/export?format=json` — node-link JSON.
- `GET /api/graph/export?format=cypher` — Cypher dump.
- A CSV export per node type and per edge type (for spreadsheet users).
- A documented read-only Cypher endpoint (`POST /api/graph/query`) with a query
  allowlist / cost limit, so analysts can query the graph directly.
- A versioned snapshot job: weekly, write a timestamped full export to the
  object store so the graph's evolution is itself an asset.
---
## 7. Layer 4 — Retrieval & reasoning
### 7.1 Hybrid retrieval
Given a query, retrieve in three parallel ways and fuse:
1. **Vector search** over chunks (Qdrant), filtered by `trust_tier` /
   `observed_at` when the query implies recency.
2. **Keyword/BM25 search** over chunk text (Postgres full-text or a dedicated
   index) — catches exact names, acronyms, project IDs.
3. **Graph retrieval** — identify entities mentioned in the query (entity
   linking), then traverse the graph N hops to pull connected nodes and their
   provenance documents.
Fuse with Reciprocal Rank Fusion. De-duplicate by `document_id`.
### 7.2 GraphRAG synthesis
Two modes, auto-selected by a lightweight query classifier:
- **Local mode** — for specific questions ("who runs ChatAmsterdam?",
  "which repo holds the Algoritmeregister?"). Retrieve the entity, its
  neighbourhood, and the supporting chunks; synthesise an answer with citations.
- **Global mode** — for broad questions ("what are the main themes in
  municipal AI?", "where are the white spots?"). Use the community summaries
  (5.5): map over relevant community summaries, then reduce into a final
  answer.
Every answer must:
- Cite sources inline, with URL and `trust_tier`, and a visible `observed_at`
  date.
- Flag conflicts ("tier-3 media reports X; no tier-1 confirmation").
- Never assert a fact that has no `source_document_id`.
- Offer graph-anchored follow-ups ("explore the network around BZK").
### 7.3 Open research mode (requirement 4 — open exploration)
An agentic loop for deep, open-ended questions:
1. Decompose the question into sub-questions.
2. For each, run hybrid retrieval + graph traversal.
3. Identify gaps; if a gap maps to a known-but-not-yet-ingested source,
   trigger an on-demand ingestion of that source.
4. Synthesise a structured, cited research brief.
5. Offer export (Section 9.6).
Cap the loop (max sub-questions, max tool calls) and stream progress to the UI.
### 7.4 Journey runner (requirement 4 — fixed journeys)
A **journey** is a declarative, multi-step flow stored as data (JSON in the
`journeys` table), not code, so journeys can be added/edited without a deploy.
```json
{
  "id": "find-who-built-x",
  "title": "Wie heeft dit al gebouwd?",
  "description": "Vind bestaande initiatieven, hun makers en contactpersonen voor een type oplossing.",
  "steps": [
    { "id": "topic",   "type": "user_input",
      "prompt": "Welk type oplossing zoek je? (bijv. chatbot voor gemeenten)" },
    { "id": "find",    "type": "graph_query",
      "uses": "topic",
      "description": "Zoek Initiatives getagd met het thema + traverseer naar Organisation en Person." },
    { "id": "rank",    "type": "rank",
      "by": ["status", "trust_tier", "recency"] },
    { "id": "present", "type": "synthesis",
      "template": "Per match: naam, organisatie, status, contactpersoon, repo, geleerde lessen." },
    { "id": "next",    "type": "suggest_followups" }
  ]
}
```
The runner executes steps in order, pausing at `user_input` steps. Step types:
`user_input`, `graph_query`, `hybrid_retrieval`, `rank`, `synthesis`,
`suggest_followups`, `branch`. The actual journey *content* is defined later by
the product owner — build the runner and ship 2–3 example journeys (e.g.
"Wie heeft dit al gebouwd?", "Leg dit landschap uit voor een nieuwkomer",
"Wat zijn de regels voor mijn AI-project?").
---
## 8. API surface (backend)
FastAPI. All responses include citations where they carry facts.
```
# Chat & retrieval
POST /api/chat                  stream a GraphRAG answer (SSE)
POST /api/research              start an open-research run (SSE progress)
GET  /api/search?q=             hybrid structured search
# Journeys
GET  /api/journeys              list journey definitions
POST /api/journeys/{id}/run     start/continue a journey run
GET  /api/journeys/{id}         get one definition
# Graph
GET  /api/graph/node/{id}       node + neighbourhood
GET  /api/graph/subgraph?...    filtered subgraph for the explorer
GET  /api/graph/export          export (graphml|json|cypher|csv)
POST /api/graph/query           allowlisted read-only Cypher
# Entities
GET  /api/initiatives           list/filter
GET  /api/organisations         list/filter
GET  /api/people                list/filter
GET  /api/repositories          list/filter
GET  /api/frameworks            list/filter
# Admin / ops
GET  /api/admin/sources         source registry
POST /api/admin/sources         add a source
GET  /api/admin/review-queue    discovery + merge review queues
POST /api/admin/review/{id}     approve/reject
GET  /api/admin/ingestion-runs  run history + errors
GET  /health   GET /metrics
```
---
## 9. Layer 5 — Interface (requirement 5 — best-in-class UX)
Next.js 14 App Router, TypeScript strict, responsive. Calm, information-dense
but not cluttered. Dutch UI copy. Light/dark mode.
### 9.1 Global shell
- Left sidebar: Chat · Verkennen (graph) · Zoeken · Journeys · Bronnen ·
  (admin behind a flag).
- Persistent command palette (`Cmd/Ctrl-K`): jump to any entity, journey, or
  action.
- Global search box in the top bar.
### 9.2 Chat / GraphRAG view
- Streaming answers.
- **Citations are first-class**: each cited claim has an inline marker;
  hovering shows source title, URL, `trust_tier`, and `observed_at`. A
  side panel lists all sources for the answer.
- Below each answer: **"entiteiten in dit antwoord"** — chips for every graph
  node referenced; clicking a chip opens it in the graph explorer.
- Suggested follow-up questions, graph-anchored.
- Conflict callouts rendered as distinct, visible notices.
### 9.3 Structured search
- Faceted: filter by `government_layer`, `org_type`, `status`, `theme`,
  `kind`, year, `trust_tier`.
- Results as cards (initiative / organisation / person / repo / framework)
  with the key fields visible.
- Each result card links to its graph node and its sources.
- Empty/low-confidence states clearly communicated.
### 9.4 Graph explorer (the centrepiece)
- **Overview canvas**: Sigma.js + graphology for the full/large graph;
  WebGL rendering, smooth pan/zoom, clustering by community.
- **Detail view**: Cytoscape.js for a focused N-hop neighbourhood around a
  selected node.
- Node colour = node type; node size = degree/centrality; edge style = edge
  type. A legend is always visible.
- Click a node → side panel with all properties, sources, and a
  "vraag de chatbot over dit knooppunt" button.
- Filters: by node type, government layer, theme, time range
  (use `observed_at` / `valid_from`).
- "Pad tussen twee knooppunten" tool: pick two nodes, show shortest path(s) —
  great for "how is this consultant's project connected to X?".
- Time scrubber: replay how the graph grew (uses `first_observed_at`).
- Performance: must stay smooth at 5.000+ nodes (cluster/aggregate above that).
### 9.5 Journeys view
- Gallery of journey cards.
- Running a journey renders as a guided, stepwise flow with progress; each
  step's output is shown before the next; results link into graph + sources.
### 9.6 Learning & synthesis features
- **Save & collections**: bookmark nodes, answers, and search results into
  named collections.
- **Export**: any answer, research brief, or collection exports to Markdown and
  PDF, with full citations and a "geraadpleegd op" date.
- **Glossary mode**: hovering an acronym (BZK, IAMA, ICAI, AIC4NL, …) shows a
  definition sourced from a `Framework`/`Organisation` node.
- **"Leg uit voor een nieuwkomer"** toggle: reframes any answer at an
  onboarding level — the core use case for the external-consultant persona.
- **Freshness indicator**: every entity view shows when it was last confirmed
  by a crawl.
### 9.7 UX principles
- Never a dead end: every view offers a next step (related nodes, follow-up
  questions, a journey).
- Trust is visible: tier and date always shown next to facts.
- Progressive disclosure: summary first, detail on demand.
- Fast: search results < 300 ms perceived; stream long answers.
- Accessible: keyboard navigable, WCAG AA contrast, screen-reader labels on the
  graph canvas (provide a list-view fallback of any subgraph).
---
## 10. Orchestration & observability
- **Scheduling**: Celery beat runs each source on its `schedule`. Discovery
  agent weekly. Community detection after each successful ingestion batch.
  Graph snapshot weekly.
- **Logging**: structured JSON; every ingestion run, extraction call, and
  retrieval gets a trace ID.
- **Metrics** (`/metrics`): documents ingested, nodes/edges created/updated,
  extraction failures, crawl errors per source, retrieval latency, LLM token
  spend.
- **Admin dashboard**: ingestion-run history, per-source health, review
  queues, graph stats over time.
- **Alerting**: a source failing N consecutive runs, extraction error rate
  above a threshold, or graph node count dropping unexpectedly raises an alert.
---
## 11. Evaluation
Build a `pytest`-based eval harness from day one.
- **Ingestion evals**: golden set of ~20 known initiatives (from the research
  report) — assert they appear as nodes with correct type, status, and at least
  one correct relation after ingestion.
- **Extraction evals**: a labelled set of source snippets → expected
  entities/relations; measure precision/recall; fail CI if below threshold.
- **Retrieval evals**: a question set with known-correct source documents;
  measure recall@k and citation correctness.
- **Answer evals**: an LLM-as-judge rubric scoring groundedness (no uncited
  claims), correctness, and completeness against reference answers.
- **Graph integrity checks** (run after every ingestion): no node without
  provenance, no edge with `confidence` null, controlled-vocabulary values
  only, no orphan `Document` nodes.
---
## 12. Build plan — phased
Work in this order. Stop after each phase, run its acceptance checks, summarise.
**Phase 0 — Scaffolding.** Monorepo, docker-compose (Neo4j, Qdrant, Postgres,
Redis, MinIO), `.env.example`, FastAPI + Next.js skeletons, CI with lint +
type-check + tests.
*Accept:* `docker-compose up` brings up all services; `/health` is green.
**Phase 1 — Schema & storage.** Implement Section 5 schema in `extraction/
schema.py`, the `GraphStore` interface + Neo4j impl, the idempotent
`writer.py`, Postgres models. Seed canonical-org table + theme vocab.
*Accept:* can create/merge/query each node and edge type; integrity checks pass.
**Phase 2 — Ingestion (structured sources).** Source registry + seed YAML.
Connectors: `innovatiebudget`, `algoritmeregister`, `github_org`, `icai_labs`.
Pipeline steps 1–7. Scheduler.
*Accept:* a scheduled run ingests all four sources; documents + chunks + raw
snapshots stored; re-running creates no duplicates.
**Phase 3 — Extraction & graph build.** LLM entity/relation extractor against
the schema, entity resolver, pipeline steps 8–10, community detection +
summaries.
*Accept:* the 20-initiative golden set appears correctly in the graph;
extraction evals pass threshold; every node has provenance.
**Phase 4 — Retrieval.** Hybrid retrieval, GraphRAG local + global, the
chat API with streaming + citations.
*Accept:* retrieval evals pass recall@k; answers carry correct citations and
never assert uncited facts.
**Phase 5 — Frontend core.** Global shell, chat view with citations + entity
chips, structured search.
*Accept:* a user can ask a question, get a cited streamed answer, and click
through to entities.
**Phase 6 — Graph explorer.** Sigma.js overview + Cytoscape detail, filters,
path tool, time scrubber, node side panel.
*Accept:* smooth at 5.000+ nodes; node click → panel → chat works.
**Phase 7 — Journeys & research.** Journey runner + 2–3 example journeys; open
research loop; export to Markdown/PDF; collections.
*Accept:* example journeys run end-to-end; a research brief exports with
citations.
**Phase 8 — Discovery & ops.** Discovery agent + review queue; generic_html /
rss / pdf connectors; admin dashboard; alerting; graph export endpoints +
weekly snapshot.
*Accept:* discovery agent proposes new sources into the review queue;
graph exports in all four formats; alerts fire on simulated failures.
---
## 13. Definition of done
- `docker-compose up` runs the entire stack from clean.
- A scheduled ingestion populates the graph from all seed sources without
  manual steps; re-running is idempotent.
- The discovery agent proposes new sources into a review queue weekly.
- The knowledge graph is queryable directly and exportable in GraphML, JSON,
  Cypher, and CSV.
- Chat answers are streamed, grounded, and cited with tier + date; uncited
  facts never appear.
- Graph explorer, structured search, journeys, and open research all work and
  cross-link.
- All evals (Section 11) pass in CI; `ingestion/` and `graph/` ≥70% coverage.
- `README.md` documents setup, the source registry, how to add a connector,
  how to add a journey, and the graph schema.
---
## 14. Appendix — seed knowledge
The project knowledge already contains a research report on the Dutch
government digital-innovation landscape. Use it to:
- Seed the canonical-organisation lookup table (BZK, ICTU, VNG, AIC4NL, ICAI,
  and their alias forms).
- Seed the `Theme` controlled vocabulary (AI, generatieve AI, algoritmes,
  datagedreven werken, Common Ground, open source, digitale dienstverlening,
  digitale ethiek, machineleesbare wetgeving, …).
- Build the 20-initiative golden set for ingestion evals (Algoritmeregister,
  ChatAmsterdam, GPT-NL, de AI-bende, DATAPRO112, AI Lab voor de Publieke
  Diensten, Innovatiebudget projects, …).
- Pre-populate the seed `sources.yaml`.
Treat the report as tier-2 seed knowledge: it bootstraps the graph, but every
fact must still be re-confirmed by a tier-1 crawl and carry its own provenance.
