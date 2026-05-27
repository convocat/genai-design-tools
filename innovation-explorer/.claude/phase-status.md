# Phase status

**Current phase:** Phase 0 — Scaffolding
**Status:** 🟡 Ready (not started)
**Started:** —
**Last touched:** 2026-05-27 (spec upgraded to v2)

---

## Phase 0 — Scaffolding (v2)

**Spec reference:** SPEC.md §14 (Phase 0) and §2.3 (repo layout).

**Acceptance checks** (must all pass before `/phase-close` will advance):

- [ ] Repo layout matches §2.3: `backend/` (with `cost/`, `agents/`, `mcp/`, `ingestion/`, `extraction/`, `graph/`, `retrieval/`, `hooks/`, `models/`, `tasks/`), `frontend/`, `data/seed/`, `docker-compose.yml`, `.env.example`, `README.md`.
- [ ] `docker-compose up` from a clean clone brings up Neo4j 5 Community, Qdrant, Postgres 16, Redis, MinIO — all healthy.
- [ ] Backend FastAPI skeleton serves `GET /health` returning 200 with each dependency's status.
- [ ] Backend exposes `GET /metrics` (Prometheus-compatible).
- [ ] Frontend Next.js 14 (App Router, strict TS) skeleton serves a landing page; `/dashboard` route stub exists.
- [ ] CI workflow runs on push: Python lint (ruff) + type-check (mypy) + pytest; TS lint (eslint) + type-check + jest/vitest.
- [ ] `.env.example` lists every required variable; `.env` is git-ignored.
- [ ] Pre-Phase-0 ADRs decided: ADR-001 (accepted: Claude + caps), ADR-002, ADR-003 (see decisions.md).

**Active blockers:** —

**Notes:**
- v2 architecture: hybrid multi-agent on Claude Agent SDK + FastMCP + Batch API + cost gateway. See memory `project_stack`, `project_cost_engineering`, `project_hybrid_principle`.
- All components must be free/OSS — see memory `feedback_free_oss_only`. Claude API is the one paid exception, gated by `cost/gateway.py` from Phase 1.
- This phase is held until Maaike manually triggers it. Do not start Phase 0 work in a session that did not explicitly open with "start phase 0".

---

## Phase history

*(empty — no phases closed yet)*

---

## Spec upgrade log

- **2026-05-27** — Switched from SPEC v1 (deterministic Celery pipeline) to SPEC v2 (hybrid multi-agent on Claude Agent SDK, with explicit cost engineering and management dashboard). v1 archived at `.claude/SPEC-v1.md`. Driver: cost discipline as primary engineering constraint + better operator surface. ADR-001 resolved as part of the switch.
