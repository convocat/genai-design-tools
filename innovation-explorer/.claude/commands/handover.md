# /handover

Generate a session handover for the Innovatie-explorer and write it both to `.claude/handover/` and `.claude/backlog.md`.

## What this does

Produces two distinct outputs:

1. **Session sign-off** — what was done, decided, and wrapped up. Closes the current session.
2. **Next session brief** — remaining or new work as a backlog entry, with a ready-to-paste opening message for the next thread.

The two are kept separate. Per Maaike's handover-clarity rule, never blur the session that just ended with the session being addressed.

---

## Steps

### Step 1: Gather info

AskUserQuestion:

1. **What was this session about?** (short title) — pre-fill from recent conversation.
2. **What's the status of the remaining work?**
   - 🟡 Ready: clear next step, next session can start immediately
   - 🔵 In progress: work ongoing, next session picks up mid-task
   - 🟠 Parked: blocked / deprioritized / waiting
   - ✅ Done: everything wrapped, no backlog entry needed
3. **Did any decisions land that need an ADR?** Yes / No. If yes, prompt to run `/decision` before continuing.

### Step 2: Generate the handover

If ✅ Done: output only Part 1, skip Part 2 and the file writes.

Otherwise output both parts clearly labelled:

**Part 1 — Session sign-off**

A short paragraph: what shipped, what was decided (with links to ADRs if any), what was left open, current phase status. Closes the current session.

**Part 2 — Next session brief**

```markdown
## [STATUS EMOJI] [Title]
*[Date] · Phase N*

[2-4 sentences: what to pick up, what to do first, any blockers]

**Key files:** [list]
**Relevant SPEC sections:** [e.g. §5.2, §12 Phase 1]
**Open ADRs:** [list if any]

**Opening message for next session:**
> [1-2 sentence version of the above, ready to paste as the first message in a new thread. Include the phase number.]
```

Show both parts to the user. Ask: **"Write to handover/ and prepend to backlog?"**

### Step 3: Write the files

If approved:
- Write the full two-part note to `.claude/handover/YYYY-MM-DD-short-title.md` (if a file with that name exists, append `-2`, `-3`).
- Prepend the Part 2 entry to `.claude/backlog.md` under 🔵 In progress (if status is in-progress), under 🟡 Ready (if ready), or under 🟠 Parked. Update phase-status.md `Last touched` to today's date.

### Step 4: Git

Do **not** commit/push automatically. Ask Maaike whether to commit. If yes:

```
git add .claude/handover/<file> .claude/backlog.md .claude/phase-status.md
git commit -m "Handover: [title]"
```

No Co-Authored-By. Do not push without explicit approval.

### Step 5: Done

Tell Maaike where the handover lives (path) and remind her to copy the opening-message text as the first line of the new session.

---

## Conventions

- Sign-off and next-session brief are distinct sections. Address them as two different moments.
- Date format: YYYY-MM-DD.
- No em-dashes.
- Status emojis: 🟡 ready · 🔵 in progress · 🟠 parked · ✅ done.
- Keep handover text tight — enough to resume, not a full summary.
