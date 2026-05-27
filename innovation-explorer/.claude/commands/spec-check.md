# /spec-check

Answer "are we still building what the spec says?" Reports drift between SPEC.md, the decisions log, and the current code state. Run before phase close and at the start of any long session.

---

## Steps

### Step 1: Load the contract

Read in parallel:
- `.claude/SPEC.md` (the frozen contract)
- `.claude/decisions.md` (sanctioned deviations)
- `.claude/phase-status.md` (where we think we are)

### Step 2: Inventory the code state

For the current phase, identify the relevant code paths from SPEC §2.2 and walk them:

- **Phase 1+:** `backend/app/extraction/schema.py`, `backend/app/graph/` — does the schema match SPEC §5?
- **Phase 2+:** `backend/app/ingestion/connectors/`, `data/seed/sources.yaml` — do connectors match §4.2?
- **Phase 3+:** extractor + resolver — do they enforce controlled vocabs from §5.1?
- **Phase 4+:** `backend/app/retrieval/` — do hybrid + GraphRAG match §7.1, §7.2?
- **Phase 5+:** `frontend/app/` — do views match §9?

For each check, look for:
1. **Missing surface area** — spec calls for X, code has no X. Flag.
2. **Silent deviation** — code does Y where spec says X, with no ADR. Flag as drift.
3. **Sanctioned deviation** — code does Y where spec says X, ADR-NNN authorises it. Verify the `# DESIGN-DECISION: ADR-NNN` comment is present at the deviation point. Flag if missing.

### Step 3: Drift report

Output:

```
## Spec-check — [date] · Phase N

### Matches spec ✅
- ...

### Sanctioned deviations (ADR-backed) ⚙️
- ADR-NNN: ... · code at <path:line> · marker [present | MISSING]

### Drift (silent deviations) ⚠️
- <path:line> — spec §X.Y says A, code does B, no ADR. Action: write `/decision` or revert.

### Missing surface area ❌
- §X.Y calls for Z; not implemented yet (expected in Phase M, current is N — OK / late)

### Hard-constraint check ✅/❌
- Free/OSS only: [pass | violations: ...]
- No secrets in repo: [pass | violations: ...]
- Dutch corpus / English code: [pass | violations: ...]
```

### Step 4: AskUserQuestion (only if drift is found)

For each drift item, ask:

1. **How to resolve drift at `<path:line>`?**
   - Write an ADR via `/decision` (sanction the deviation)
   - Revert / fix to match spec
   - Defer (add a 🟡 item to backlog.md)

### Step 5: Done

Print summary line: "X matches · Y ADR-backed · Z drift · W missing." Suggest `/phase-close` only if drift is zero and the current phase's acceptance checks are ticked.

---

## Conventions

- Don't infer ADRs from comments. An ADR exists in decisions.md or it doesn't.
- Don't propose code edits in this command. It reports; resolution happens in other commands.
- "Missing surface area" expected in a later phase is not drift. Only flag if late.
