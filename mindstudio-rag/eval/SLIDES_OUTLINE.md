# Slide deck outline — Evals for an LLM bot in 40 minutes

Audience: conversation designers / prompt engineers, beginner-level.
Format: ~28 slides, ~40 minutes including a live demo on the MindStudio RAG bot.
Companion files: `DEMO_GUIDE.md`, `demo_baseline_questions.csv`, `LANGFUSE_DATASET_TUTORIAL.md`.

Each slide block below lists: **title**, then **bullets** (what's on the slide), then *Speaker note* in italics with how long to spend.

---

## Section A — Why evals (0–5 min)

### 1. Title slide
- "Evals for LLM bots — finding bugs that tests can't"
- Your name / date

*Speaker note: 30 sec. Don't over-introduce.*

### 2. Three ways LLM products fail
- Hallucination — invents facts that sound right
- Instruction drift — slowly stops following the system prompt
- Unsafe output — complies with prompt injections or leading questions

*Speaker note: 60 sec. Use one short real example per bullet if you have one.*

### 3. Why unit tests can't catch any of these
- Unit tests check exact strings
- LLM outputs are semantic, not deterministic
- "The answer mentions pricing" is true or false in a way assertEqual cannot express

*Speaker note: 45 sec.*

### 4. What evals are, in one sentence
- An eval = dataset + run + score, on repeat

*Speaker note: 30 sec. Land this hard, you'll refer back to it.*

---

## Section B — The mental model (5–12 min)

### 5. The three pieces
- **Dataset**: fixed list of inputs
- **Run**: execute the bot on every input, record the output
- **Score**: grade each output against a rubric

*Speaker note: 60 sec. Show as a diagram if you can.*

### 6. The loop
- Diagram: Dataset → Run → Score → Compare → Fix prompt → Run → …
- The comparison is what tells you you're improving

*Speaker note: 90 sec. Emphasise that absolute scores are less interesting than deltas between runs.*

### 7. Manual vs. LLM-as-judge
- Manual: slow, expensive, accurate, teaches you the rubric
- LLM-as-judge: fast, cheap, 85–95% accurate
- Always manual first; promote to a judge once the rubric is stable

*Speaker note: 90 sec.*

### 8. The MindStudio bot, briefly
- Architecture sketch: question → HyDE → graph retrieval → answer with `[n]` citations
- Why this is hard to test: every step can fail differently

*Speaker note: 60 sec. Use the trace tree screenshot.*

### 9. The rubric we'll use today
- `correctness`: correct / partial / wrong / refused_correctly
- `citation`: true / false (did every claim cite `[n]`)
- `safety`: safe / risky / harmful

*Speaker note: 60 sec. Tell them they'll use these in 10 minutes.*

---

## Section C — Live demo, broken baseline (12–25 min)

### 10. "I broke the prompt on purpose"
- For the demo, the bot is running on a sabotaged system prompt
- Three sabotages: no citation rule, "guess if unsure", encourages emoji
- Goal: produce visible failures we can score

*Speaker note: 30 sec.*

### 11. Show the broken prompt
- Screenshot of `answer-system-prompt-DEMO-BROKEN.md`
- Point out exactly which lines were changed vs. the good prompt

*Speaker note: 90 sec.*

### 12. The demo dataset
- 15 questions, hand-picked to expose the sabotage
- Mix: hallucination_bait, out_of_scope, procedural, conceptual, multi_hop, problematic_*, edge_format
- Show the CSV

*Speaker note: 60 sec.*

### 13. Live: import the dataset
- Langfuse → Datasets → Upload CSV
- Map columns
- (Switch to live Langfuse)

*Speaker note: 90 sec. Practice this once beforehand so it doesn't fumble.*

### 14. Live: trigger the baseline run
- Hit Run, watch traces appear
- While it runs (~2 min), talk through what's about to happen

*Speaker note: 2 min, including filler.*

### 15. Live: score the run with the audience
- Click into 5–6 traces, score together
- Use keyboard shortcuts
- Highlight: every non-refusal trace fails `citation`

*Speaker note: 4 min. This is the heart of the demo. Let the audience disagree on edge cases.*

### 16. Recap: what we saw
- 15 traces, X cited (out of Y that should have)
- Hallucinations on out-of-scope questions: count them
- Safety controls held: good (broken prompt didn't break safety)

*Speaker note: 60 sec.*

---

## Section D — Fix and compare (25–33 min)

### 17. The fix: restore the good prompt
- Show the diff: re-add citation rule, "if unsure say so", remove emoji licence
- Save as new version, label `demo-fix-v1`

*Speaker note: 90 sec.*

### 18. Live: rerun the dataset
- Trigger run named `fix-v1`
- Talk through what we expect to improve

*Speaker note: 2 min.*

### 19. Live: compare runs
- Langfuse → Datasets → Compare runs → pick the two
- Walk down the rows; ask audience to call Improved / Same / Regressed
- Land: no regressions on `problematic_*`, big improvements on `citation`

*Speaker note: 3 min. The visual side-by-side is the whole point. Spend time here.*

### 20. The decision rule
- Ship if: zero regressions on `problematic_*` AND more improvements than regressions overall
- Otherwise: iterate

*Speaker note: 60 sec.*

---

## Section E — LLM-as-judge (33–38 min)

### 21. "Now do this 70 times a week"
- Scaling manual scoring doesn't work
- Turn the rubric you just used into a judge prompt

*Speaker note: 30 sec.*

### 22. The judge prompt
- Show the `correctness` judge prompt from `LANGFUSE_DATASET_TUTORIAL.md`
- Variables: `{{input}}`, `{{output}}`
- Output: JSON with score + reason

*Speaker note: 90 sec.*

### 23. Calibration
- Run the judge on the 15 items we just scored
- Compare judge scores to your manual scores
- ≥ 13/15 agreement = trustworthy; less = refine the prompt

*Speaker note: 90 sec.*

### 24. What stays manual, forever
- Safety category for release gates
- Anything where the rubric is still changing
- Brand-new failure modes you haven't seen yet

*Speaker note: 60 sec.*

---

## Section F — Wrap (38–40 min)

### 25. The loop again
- Repeat the diagram from slide 6
- Highlight that you've now walked through every box

*Speaker note: 30 sec.*

### 26. Cadence
- After any prompt edit: run the full set
- Weekly: run a 10-item sample
- Before any demo: run the full set + manual sweep of safety category

*Speaker note: 45 sec.*

### 27. Where things live
- `eval/test_questions.csv` — full 70-item set
- `eval/demo_baseline_questions.csv` — 15-item teaching subset
- `eval/DEMO_GUIDE.md` — this script in prose
- `eval/LANGFUSE_DATASET_TUTORIAL.md` — reference manual
- Langfuse → Datasets / Prompts / Evaluators — the live tools

*Speaker note: 30 sec.*

### 28. Q&A
- One slide, big "Questions?"
- Common questions in `DEMO_GUIDE.md` Part 4

*Speaker note: whatever time is left.*

---

## Timing summary

| Section | Slides | Minutes |
|---|---|---|
| A — Why evals | 1–4 | 5 |
| B — Mental model | 5–9 | 7 |
| C — Broken baseline demo | 10–16 | 13 |
| D — Fix and compare | 17–20 | 8 |
| E — LLM-as-judge | 21–24 | 5 |
| F — Wrap | 25–28 | 2 |
| **Total** | **28** | **40** |

## Things to prepare before going on stage

- Bot is up and reachable from your laptop.
- Langfuse project is open in a browser tab, logged in.
- Broken prompt is already loaded as version `demo-baseline-broken` (see `DEMO_GUIDE.md` Step 0).
- Score configs are created (Step 2).
- Dataset is empty so you can demo the import live — or pre-imported if you want to save 3 minutes.
- Backup screenshots of the trace tree, compare-runs view, and a sample judge output, in case the demo gods are unkind.
