# 2026-05-27 — Project scaffolding + spec v1→v2 switch

## Part 1 — Session sign-off

Set up the project-management scaffolding for Innovatie-explorer from scratch: memory (11 files at `~/.claude/projects/.../memory/`), repo `.claude/` directory with frozen SPEC contract, backlog, decisions log, phase-status, handover index, and six slash commands (`/backlog`, `/handover`, `/phase-start`, `/phase-close`, `/decision`, `/spec-check`). Read both spec drafts (v1 deterministic Celery, v2 hybrid multi-agent). Recommended v2 with reasoning; Maaike accepted. Archived v1 at `.claude/SPEC-v1.md`, swapped `.claude/SPEC.md` to v2, refreshed memory (added `project_cost_engineering` and `project_hybrid_principle`, updated phases/stack/spec-reference), refreshed backlog and phase-status for v2's 9-phase plan. Recorded **ADR-008** (adopt SPEC v2 over v1) and **ADR-001** (Claude API with budget caps + cost gateway as the only paid line item). Six open ADRs queued for resolution before relevant phases: 002 (embeddings model), 003 (Docker runtime), 004 (cost-gateway lint mechanism), 005 (Batch vs sync policy), 006 (model-tier defaults from current docs), 007 (Redis vs Valkey). No code written — pure scaffolding. Phase 0 sits 🟡 Ready awaiting manual trigger.

## Part 2 — Next session brief

🟡 **Project scaffolding + spec v1→v2 switch** · Phase 0

Scaffolding is complete and SPEC v2 (hybrid multi-agent + cost discipline) is the frozen contract. Phase 0 (docker-compose + FastAPI/Next.js skeletons + CI) sits 🟡 Ready in the backlog. The next session starts Phase 0 — but resolve ADR-003 (Docker runtime on Windows) first via `/decision`, and check whether ADR-002 (embeddings) needs to land before Phase 2 or can wait. Confirm with Maaike before starting any code.

**Key files:**
- `.claude/SPEC.md` (v2, frozen) · `.claude/SPEC-v1.md` (archived)
- `.claude/backlog.md` · `.claude/phase-status.md` · `.claude/decisions.md`
- `.claude/commands/` (six commands)
- `~/.claude/projects/C--Sharing-Maaike-Innovatie-explorer/memory/` (13 files)

**Relevant SPEC sections for Phase 0:** §2.3 (repo layout), §14 Phase 0 acceptance.

**Open ADRs:** 002 (embeddings, before Phase 2), 003 (Docker runtime, before Phase 0), 004-007 (later phases).

**Accepted ADRs landed this session:** ADR-001 (Claude + cost gateway), ADR-008 (adopt SPEC v2 over v1).

**Opening message for next session:**

> Innovatie-explorer Phase 0 — scaffolding the monorepo + docker-compose stack per SPEC v2 §14. Read `.claude/backlog.md` + `.claude/phase-status.md` + memory `project_phases` + `project_stack` first. Resolve ADR-003 (Docker runtime on Windows) via `/decision` before writing the compose file. No code yet — confirm scope with me, then `/phase-start 0`.
