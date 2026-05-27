# Innovatie-explorer backlog

**Current phase:** Phase 0 — Scaffolding (🟡 Ready, not started)
**Spec contract:** [SPEC.md](./SPEC.md) (v2 — hybrid multi-agent) — frozen. v1 archived at [SPEC-v1.md](./SPEC-v1.md). Deviations go to [decisions.md](./decisions.md), never edits to SPEC.md.
**Hard constraints:** free/OSS only (Claude API is the one paid exception, gated by the cost gateway); hybrid principle (deterministic by default, agentic by exception).

Statuses: 🔵 In progress · 🟡 Ready · 🟠 Parked · ✅ Done

---

## 🔵 In progress

*(nothing yet)*

---

## 🟡 Ready (Phase 0)

### 🟡 Project scaffolding + spec v1→v2 switch — handover
*Added 2026-05-27 · Last touched 2026-05-27 · [handover note](./handover/2026-05-27-project-scaffolding-and-spec-v2-switch.md)*

Scaffolding complete; SPEC v2 frozen as the contract. ADR-001 (Claude + cost gateway) and ADR-008 (adopt v2 over v1) accepted. Next session: resolve ADR-003 (Docker runtime on Windows) via `/decision`, then `/phase-start 0`. No code yet.

**Opening message for next session:**

> Innovatie-explorer Phase 0 — scaffolding the monorepo + docker-compose stack per SPEC v2 §14. Read `.claude/backlog.md` + `.claude/phase-status.md` + memory `project_phases` + `project_stack` first. Resolve ADR-003 (Docker runtime on Windows) via `/decision` before writing the compose file. No code yet — confirm scope with me, then `/phase-start 0`.

---

### 🟡 Phase 0 — Scaffolding
*Added 2026-05-27 · Last touched 2026-05-27*

Bootstrap the monorepo and docker-compose so all services come up green from a clean clone.

**Acceptance (from SPEC §14 Phase 0):**
- [ ] Monorepo layout matches SPEC §2.3 (`backend/`, `frontend/`, `data/seed/`, `docker-compose.yml`, `.env.example`, `README.md`).
- [ ] docker-compose brings up Neo4j 5 Community, Qdrant, Postgres 16, Redis, MinIO from clean.
- [ ] FastAPI skeleton runs and exposes `/health` (green) and `/metrics`.
- [ ] Next.js 14 App Router skeleton runs.
- [ ] CI runs lint + type-check + tests on push.
- [ ] `.env.example` committed; `.env` git-ignored.

**Pre-Phase-0 decisions to record in [decisions.md](./decisions.md):**
- ADR-001: LLM provider — Claude with budget caps (✅ accepted: Claude + cost gateway, per Maaike's v2 decision on 2026-05-27).
- ADR-002: Embeddings model — pick OSS multilingual (e5-large vs bge-m3) before Phase 2.
- ADR-003: Docker runtime on Windows — Docker Desktop vs Rancher Desktop vs Docker Engine on WSL2.

**Key files (to be created):**
- `docker-compose.yml`, `.env.example`, `.gitignore`
- `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/config.py`
- `frontend/package.json`, `frontend/app/`
- `.github/workflows/ci.yml`

---

## 🟠 Parked

*(nothing yet)*

---

## ✅ Done (this phase)

*(nothing yet — Phase 0 has not started)*

---

## Future phases (v2)

These live in SPEC §14; one line each here for orientation. `/phase-start <n>` expands the chosen one into 🟡 Ready items.

| # | Phase | Highlights |
| - | --- | --- |
| 1 | Cost gateway & schema | `cost/gateway.py` + ledger + budget caps; §7 schema; GraphStore + Neo4j; idempotent writer; lint check (nothing imports Anthropic SDK except gateway) |
| 2 | Deterministic spine | Source registry + seed YAML; 4 connectors; pipeline steps 1-9; change detection; embedding cache; scheduler. **Zero LLM cost in this phase.** |
| 3 | MCP servers | Graph, Vector, Web, GitHub, SQL FastMCP servers; scoped allowlists |
| 4 | Knowledge-plane agents | Extractor (Batch + prompt caching + extraction cache), selective Critic, Graph steward, incremental community detection. Budget + telemetry hooks. |
| 5 | Query-plane agents | Planner (Tier-A classifier), deterministic hybrid retrieval, retrieval squad, Synthesizer, answer cache, chat API with streaming citations |
| 6 | Frontend explorer | Shell, chat with citations + entity chips, structured search, graph explorer (Sigma + Cytoscape, filters, path tool, time scrubber) |
| 7 | Journeys, research, Scout | Journey runner + 2-3 example journeys, Research agent (bounded loop), Scout + discovery, Markdown/PDF export, collections |
| 8 | Management dashboard | All §12.8 panels (cost, agent activity, graph health, source freshness, review queues, evals, usage, manual controls), what-if estimator, graph exports + weekly snapshot, alerting |
