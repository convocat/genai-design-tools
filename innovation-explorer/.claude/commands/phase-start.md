# /phase-start

Bootstrap a build phase: copy its acceptance checks into `phase-status.md`, expand it into ready items in `backlog.md`, and confirm before starting work.

## Arguments

`/phase-start <n>` where `<n>` is 0-8. If omitted, prompt the user.

---

## Steps

### Step 1: Validate

- Read `.claude/phase-status.md`. If the current phase is not closed (no entry in "Phase history" for `n-1`), refuse and tell Maaike to run `/phase-close` first. Exception: phase 0, which has no predecessor.
- Read `.claude/decisions.md`. List any "Open decisions" whose "before Phase N" is `<= n`. If any are still open, list them and ask: **"These ADRs are unresolved. Resolve them now (`/decision`) or proceed anyway?"**

### Step 2: Re-read the spec

Read `.claude/SPEC.md` §12 for the target phase + any cross-referenced sections (e.g. Phase 1 references §5; Phase 4 references §7.1, §7.2; Phase 6 references §9.4).

### Step 3: Re-read B3 de-scope notes

Read the approved plan file (path: the project's plan file) and consult the **B3 — sequence/de-scope** list for the target phase. Per Maaike's decision, scope is decided at `/phase-start`, not pre-baked. Surface the B3 suggestions for this phase.

### Step 4: Propose a scope and a task breakdown

Output:

```
## Phase N — [title]

**Acceptance checks (from SPEC §12):**
- [ ] ...
- [ ] ...

**B3 de-scope suggestions for this phase:**
- ...

**Proposed task breakdown (🟡 Ready items):**
1. ...
2. ...
3. ...
```

Tasks must be < 1 session each (split if larger). Use English titles. Reference SPEC section numbers.

### Step 5: Confirm with Maaike

AskUserQuestion:

1. **Accept this scope and task breakdown?**
   - Yes — write to phase-status.md and backlog.md
   - Modify — show me where to edit
   - Cancel
2. **Which B3 de-scopes apply to this phase?** (multiSelect) — list from Step 3.

### Step 6: Write

If accepted:
- Overwrite `.claude/phase-status.md` with:
  - new "Current phase" header
  - the acceptance checks (unticked)
  - any active blockers (none unless explicitly named)
  - notes including the accepted B3 de-scopes
- Append the prior phase's status block under "Phase history" if not already there.
- Update `.claude/backlog.md`:
  - Move any leftover 🟡 items from the previous phase to 🟠 Parked with reason "deferred from Phase N-1" (or delete if explicitly resolved).
  - Add the new 🟡 items under "Ready (Phase N)".
  - Update the "Current phase" header.
- Record any B3-related scope cuts as new ADRs via `/decision` (one ADR per de-scope, e.g. "ADR-NNN — Phase 4 ships local-mode GraphRAG only").

### Step 7: Done

Print a one-line summary: "Phase N initialised with M ready items, K acceptance checks, L scope ADRs." Suggest running `/backlog` to start work.

---

## Conventions

- One phase active at a time.
- Acceptance checks come verbatim from SPEC §12 — never paraphrase.
- B3 de-scopes that are accepted become ADRs so they have a paper trail.
- Do not start coding in the same invocation. `/phase-start` only sets up.
