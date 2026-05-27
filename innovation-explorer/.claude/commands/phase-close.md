# /phase-close

Verify the current phase's acceptance checks and advance to the next phase. Refuses to advance if checks fail.

---

## Steps

### Step 1: Read current state

- `.claude/phase-status.md` — current phase + its acceptance checks
- `.claude/backlog.md` — what's still 🔵 or 🟡 in this phase

### Step 2: Run acceptance checks

For each check in `phase-status.md`:

- If it's a runnable verification (e.g. "docker-compose up brings up all services + /health green"), run it via Bash and report pass/fail.
- If it's a code/behaviour assertion (e.g. "every node has provenance"), invoke the relevant test or eval. From Phase 3 onward, this typically means running the pytest eval harness (SPEC §11).
- If it's a manual check (e.g. "smooth at 5.000+ nodes"), present it for Maaike to confirm.

Output a table:

```
| Check | Result | Notes |
| --- | --- | --- |
| docker-compose up brings services healthy | ✅ pass | |
| /health green | ✅ pass | |
| CI runs lint + type-check + tests | ❌ fail | mypy errors in app/config.py |
```

### Step 3: If any check failed, stop

Do not advance. Report failures clearly. Suggest creating 🟡 items for each failure and re-running `/phase-close` when fixed.

### Step 4: If all pass, summarise the phase

Output:

```
## Phase N — closed [date]

**Shipped:**
- ...

**Decisions landed:** ADR-NNN ... (link to decisions.md)

**Carry-over to Phase N+1:** [items, if any]
```

### Step 5: AskUserQuestion

1. **Close Phase N and open Phase N+1 now?**
   - Yes, advance — runs `/phase-start <n+1>`
   - Yes, but I'll start the next phase later — only close this one
   - Hold — don't close yet

### Step 6: Write

If closing:
- Move closed-phase block in `phase-status.md` to "Phase history" with a closure date.
- Archive ✅ Done items from `backlog.md` (move them out of the current-phase section into a "Phase N archive" section, or delete if Maaike prefers a clean board).
- If advancing: trigger `/phase-start <n+1>`.

### Step 7: Git

Ask Maaike whether to commit the phase-close changes. No auto-commit.

---

## Conventions

- Acceptance checks are non-negotiable. Failing checks block phase close.
- "Carry-over" items become 🟠 Parked or are pulled into the next phase's 🟡 — never just left in the closed phase.
- Use SPEC §12 acceptance text verbatim; don't soften.
