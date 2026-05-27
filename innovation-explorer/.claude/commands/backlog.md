# /backlog

Open a backlog grooming session for the Innovatie-explorer. Surface what needs attention in the current phase before asking what to work on.

## What this does

Reads the backlog + phase-status + decisions log, then presents a structured briefing: stale items, drifting work-in-progress, unresolved open ADRs, and a suggested focus for the session. At the end, writes any decisions back to the backlog.

Phase-aware: never proposes work from a future phase unless the current phase is closed.

---

## Steps

### Step 1: Gather context

Read these files in parallel:
- `.claude/backlog.md`
- `.claude/phase-status.md`
- `.claude/decisions.md`
- The latest file in `.claude/handover/` (if any), to know what the last session left open

### Step 2: Scan and surface

Flag each of the following if present:

**Open ADRs blocking the current phase**: in `decisions.md` under "Open decisions", any ADR whose "before Phase N" matches the current or next phase. These must be resolved before the phase can advance.

**Stale items**: any 🔵 or 🟡 item whose `Last touched` is 14+ days ago. List with the date.

**In-progress drift**: any 🔵 item that has no activity in the handover history for the last two sessions.

**Phase acceptance status**: count of acceptance checks ticked vs total, for the current phase. If all ticked, suggest `/phase-close`.

**Bundles**: any 🟡 item that contains more than one distinct deliverable. Flag for splitting.

### Step 3: Present the briefing

Output a short briefing in this format:

```
## Backlog briefing — [date]

**Current phase:** Phase N — [title] · acceptance [x/y]

### Needs attention
[list of flags from Step 2, one line each]

### Suggested focus for this session
[1-3 items ranked: unblocked + ready > stale in-progress > open ADRs]

### Board at a glance
[table: Item | Status | Last touched | Blocker]

---
**What you can do:** name an item to work on it · "park [item]" · "done [item]" · "add [description]" · "resolve ADR-NNN" · "update backlog"
```

Keep it tight. One line per flag. No preamble.

### Step 4: Confirm session intent

AskUserQuestion:

1. **What do you want to work on?** — options pre-filled from "Suggested focus" above, plus "Something else" and (if applicable) "Close the phase".

### Step 5: Work the session

Proceed with the chosen item. Use the relevant skill if one exists (`/phase-start`, `/decision`, `/spec-check`, `/handover`).

### Step 6: Update the backlog

At a natural stopping point or end of session, ask:

> "Should I update the backlog with what we decided?"

If yes:
- Update item status (🔵 / 🟡 / 🟠 / ✅), `Last touched` date, blocker field.
- Add new items discovered during the session under 🟡.
- Move completed items to ✅ Done for this phase.
- Show the diff. Do **not** commit/push automatically — Maaike controls the git workflow here. Confirm with her before any git command.

---

## Conventions

- Date format: YYYY-MM-DD.
- No em-dashes.
- Keep briefing output short: signal, not report.
- Never suggest work from a future phase while the current phase is open.
- Honor [[feedback_free_oss_only]] — any item that pulls in a non-OSS dependency must be flagged.
