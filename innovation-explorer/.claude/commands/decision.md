# /decision

Append an ADR-style entry to `.claude/decisions.md`. Use whenever code deviates from a SPEC default or makes a choice the spec leaves open.

## Argument

`/decision <short title>` — e.g. `/decision use pgvector instead of Qdrant`. If omitted, prompt.

---

## Steps

### Step 1: Determine the next ADR id

Read `.claude/decisions.md`. Find the highest existing `ADR-NNN` (across both "Open decisions" and "Accepted decisions"). New ID is `next = max + 1`, zero-padded to 3 digits.

### Step 2: Gather context

AskUserQuestion (one question with multiple parts is fine, or chain them):

1. **What spec section does this deviate from or address?** (e.g. "§2.1 — vector store choice")
2. **What options did you consider?** (free text — list at least two)
3. **What did you decide?**
4. **Why?** (the rationale — what future readers need)
5. **What does this commit us to / forbid?**
6. **Status?** — `proposed` / `accepted`

### Step 3: Append the entry

Append to `.claude/decisions.md` under "Accepted decisions" (or under "Open decisions" if status is `proposed` and there's a "before Phase N" gate):

```markdown
## ADR-NNN — <title>
*YYYY-MM-DD · Status: accepted*

**Context.** ...

**Options considered.**
- A — ...
- B — ...

**Decision.** ...

**Why.** ...

**Consequences.** ...

**Code marker.** `# DESIGN-DECISION: ADR-NNN — <one-liner>`
```

If the decision relates to one of the pre-listed Open decisions (ADR-001, 002, 003 etc.), remove it from "Open decisions" and move the resolved entry into "Accepted decisions".

### Step 4: Confirm

Show the user the appended entry. Ask whether to also drop the code marker comment at a specific file/line (if so, do it via Edit).

### Step 5: Git

Ask before committing. No auto-commit.

---

## Conventions

- Use sequential IDs. Don't skip numbers.
- One decision per ADR. If two things were decided together, write two ADRs that cross-reference.
- A superseded ADR is not deleted; mark the superseded one as `Status: superseded by ADR-NNN`.
- Code markers are short. Long rationale lives in this file, not in the source code.
