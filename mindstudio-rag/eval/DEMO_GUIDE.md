# Demo guide: running the eval loop on the MindStudio bot

A self-contained walkthrough you can use as a teaching demo. ~30 minutes hands-on, plus theory to read first.

## Part 1 — Theory (read once)

### Why evals exist

LLM-based products fail in three ways your unit tests cannot catch:

1. **Hallucination.** The model invents plausible-sounding facts that are not in your sources.
2. **Instruction drift.** The model gradually stops following rules you set in the system prompt (citing sources, staying in scope, format).
3. **Unsafe output.** The model complies with a prompt-injection or a leading question and produces content you would not stand behind.

Traditional software testing (`assertEqual(...)`) can't detect any of these because the failures are about *meaning*, not exact strings. Evals fill that gap.

### What an eval actually is

An eval is three things glued together:

| Piece | What it is | Concrete example |
|---|---|---|
| **Dataset** | A fixed list of inputs (and ideally an expected behavior, not an expected string). | `test_questions.csv` |
| **Run** | Executing the LLM system on every dataset item, recording the output. | A traced batch of 70 `/api/ask` calls. |
| **Score** | A grade per item, from a human or another LLM, against a rubric. | "Did this answer cite its sources?" → true/false |

The value comes from doing this repeatedly: every prompt change creates a new run, and you compare scores to the previous run. That comparison — not the absolute scores — tells you whether you're getting better.

### Manual scoring vs. LLM-as-judge

| | Manual | LLM-as-judge |
|---|---|---|
| Cost | High (your time) | Low (model tokens) |
| Speed | Slow | Fast |
| Accuracy | Highest, once you know the rubric | 85–95% if the judge prompt is good |
| When to use | While you're still learning what "good" looks like, and for safety-critical categories on every release | For regression sweeps after the rubric is stable |

The order matters: **manually score first**, derive the rubric, *then* hand the rubric to a judge LLM. Skipping the manual phase produces a judge that confidently grades the wrong things.

### The loop

```
   ┌─────────────────────────────────────────────┐
   │  1. Have a dataset                          │
   │  2. Run the bot against it (baseline)       │
   │  3. Score the run (manual, with a rubric)   │
   │  4. Decide what's broken; edit the prompt   │
   │  5. Run again with the new prompt           │
   │  6. Compare runs → kept? regressed? new?    │
   │  7. Ship or iterate                         │
   └─────────────────────────────────────────────┘
```

That's it. Everything else (LLM judges, dashboards, drift detection) is an optimisation of this loop, not a replacement.

---

## Part 2 — The hands-on demo

Goal: walk an audience through one full turn of the loop using a deliberately broken prompt, so that the "before" state has visible, scoreable failures.

### Prerequisites

- The MindStudio RAG bot is running and reachable.
- You have admin access to a Langfuse project that the bot is already pointed at.
- This repo's `eval/` folder is available.

### Step 0 — Stage the broken prompt (do this before the audience walks in)

1. Open Langfuse → **Prompts** → `mindstudio/answer-system-prompt`.
2. Click **New version**. Paste the contents of `prompts/answer-system-prompt-DEMO-BROKEN.md` (omit the HTML warning comment, or keep it — Langfuse will treat it as text).
3. Save. Give it the label `demo-baseline-broken`.
4. **Important**: change `langfuse_integration.get_prompt` calls to read from `demo-baseline-broken` instead of `production` for the duration of the demo. The simplest way: temporarily edit `serve.py` to pass `label="demo-baseline-broken"`, or in Langfuse promote the broken version to `production` and remember to restore the good one after.
5. Confirm the bot now answers in the broken style: ask it "What is an agent?" via the UI and check that you get an enthusiastic emoji-laden answer with no `[n]` citations.

### Step 1 — Create the demo dataset (5 min)

1. Langfuse → **Datasets** → **New dataset** → `mindstudio-demo-baseline`.
2. Upload `eval/demo_baseline_questions.csv`.
3. Map columns:
   - `question` → Input
   - `expected_behavior` → Expected output
   - `category` → Metadata
   - `what_the_broken_prompt_will_likely_do` → Metadata
4. Save. You should see 15 items.

The 15-item version is intentionally small so the demo fits in 30 minutes. The full `test_questions.csv` (70 items) is for real regression sweeps.

### Step 2 — Set up the score configs (3 min, once)

Langfuse → **Settings** → **Scores** → **New score config**. Create three:

| Name | Type | Values |
|---|---|---|
| `correctness` | Categorical | `correct`, `partial`, `wrong`, `refused_correctly` |
| `citation` | Boolean | true / false |
| `safety` | Categorical | `safe`, `risky`, `harmful` |

### Step 3 — Run the broken bot against the dataset (5 min)

Two options:

**a) From the Langfuse UI**: dataset → **New run** → name it `baseline-BROKEN`. Trigger it.

**b) Python runner**: copy the appendix script from `eval/LANGFUSE_DATASET_TUTORIAL.md`, set `RUN_NAME = "baseline-BROKEN"`, run `python eval/run_dataset.py`. 15 items take ~2 minutes.

When done, 15 new traces appear linked to the run.

### Step 4 — Score the run manually with the audience (10 min)

Open the run. Walk through the items live. For each, ask the audience: "Does this answer cite sources? Is it correct? Is it safe?"

Expected scoring against the broken prompt:

| Category | Expected manual scores |
|---|---|
| `hallucination_bait` (4 items) | `correctness=wrong`, `citation=false` |
| `out_of_scope` (2 items) | `correctness=wrong`, `citation=false` |
| `procedural` (3 items) | `correctness=correct` (steps probably exist) but `citation=false` |
| `conceptual` (2 items) | `correctness=correct` but `citation=false` |
| `multi_hop` (1 item) | `correctness=partial`, `citation=false` |
| `problematic_harm` (1 item) | `correctness=refused_correctly`, `safety=safe` (control — broken prompt didn't break safety) |
| `problematic_pii` (1 item) | `refused_correctly`, `safe` (control) |
| `edge_format` Dutch (1 item) | `correctness=wrong` (answered in English) |

Key teaching moment: the citation rule is the most visible casualty. Almost every non-refusal trace will fail `citation`.

### Step 5 — Fix the prompt (3 min)

Open `mindstudio/answer-system-prompt` in Langfuse. Create a new version that restores the discipline. The easiest fix: paste back the contents of `prompts/answer-system-prompt.md` (the good version in this repo). Save and label it `demo-fix-v1`.

Point the bot at `demo-fix-v1` (same mechanism as Step 0).

### Step 6 — Re-run and compare (5 min)

1. Trigger another run named `fix-v1`.
2. When it finishes, dataset → **Compare runs** → pick `baseline-BROKEN` and `fix-v1`.
3. Walk through side-by-side. The audience scores each row as Improved / Unchanged / Regressed.

Expected outcome:
- Citation failures → all fixed.
- Hallucinations on `hallucination_bait` and `out_of_scope` → fixed (bot refuses).
- Tone/emoji → fixed.
- Safety control cases → unchanged (still safe).

You have just shown the audience the full eval loop in one sitting.

### Step 7 — Introduce LLM-as-judge (5 min)

Now that the audience has scored 15 items by hand and seen the rubric, show how to encode that rubric as a judge prompt. Use the three starter judge prompts in `LANGFUSE_DATASET_TUTORIAL.md` → "Promoting your manual rubric to an LLM judge". Run the `correctness` judge on the same `fix-v1` run. Compare judge scores to the manual scores the audience just produced. If they agree on ≥ 13/15, the judge is calibrated and can be used for future bulk runs.

### Step 8 — Restore production (1 min, do this before you leave)

Re-point the bot at the good prompt under whichever label is your actual production label. Verify with a live question that citations are back.

---

## Part 3 — Reset checklist for re-running the demo

- Bot points back at `production` after each demo: yes/no
- `demo-baseline-broken` prompt version still exists in Langfuse: yes/no (recreate if missing)
- `mindstudio-demo-baseline` dataset still has 15 items: yes/no
- Three score configs still exist: yes/no
- Latest run cleaned up if you don't want it counted in metrics: yes/no

---

## Part 4 — Talking points if the audience asks

- **"Why not just write unit tests?"** Tests check exact outputs. LLMs vary by token. Evals score *behavior*, which is what users care about.
- **"How big should a dataset be?"** Start with 20–50 items covering your real error modes. Bigger isn't always better; coverage of failure types matters more than count.
- **"How often do you run them?"** After any prompt edit, any retrieval change, and on a weekly cadence regardless. Many teams gate releases on eval scores in CI.
- **"What about cost?"** A 70-item run on Sonnet is roughly the cost of one cup of coffee. LLM-judging adds maybe 30%. The expensive thing is *not* running them.
- **"Can the judge be wrong?"** Yes. That's why you calibrate against manual scores, and why safety categories should stay human-scored for release gates.
