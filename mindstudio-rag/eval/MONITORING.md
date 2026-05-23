# Monitoring and improving the MindStudio RAG bot

Audience: conversation designers / prompt engineers with little to no prior Langfuse experience.

This is the day-to-day workflow for watching the bot, finding bad answers, fixing them, and confirming the fix worked.

## What lives where

- **Langfuse** (https://cloud.langfuse.com): every conversation the bot has had, plus the system prompts it uses. This is where you spend almost all your time.
- **`prompts/`** in this repo: the markdown system prompts that get pushed to Langfuse. Only edit these if you want to commit a change to git as well; otherwise edit in Langfuse directly.
- **`eval/test_questions.csv`**: 50 test questions you run after any prompt change to catch regressions.

In Langfuse you will use four screens:

| Screen | What it shows | When to use it |
|---|---|---|
| **Sessions** | One row per conversation (`mindstudio-...` prefix). | "Show me real conversations users had." |
| **Traces** | One row per user turn. Click in to see HyDE / retrieval / answer steps. | "Why did the bot say *that*?" |
| **Prompts** | The current system prompts, with version history. | "I want to change how the bot behaves." |
| **Datasets** | Saved test sets. Run prompt changes against them and compare. | "Did my prompt change break anything?" |

## The weekly workflow

### 1. Sample real conversations (10 min, daily or weekly)

1. Open **Sessions** in Langfuse.
2. Filter by tag `mindstudio` and the last 7 days.
3. Open 10 random sessions. Read each conversation end to end.
4. For each one, jot a one-line verdict: **good / okay / bad** and **why**.

What "bad" usually looks like:
- Bot hallucinated something not in the sources.
- Bot refused but the answer *was* in the sources.
- Bot ignored what the user actually asked.
- Bot's tone is off (too formal, too chatty, wrong language).
- Citations missing or pointing at the wrong source.

### 2. Diagnose a bad answer (5 min per case)

When you find a bad answer, click into the trace. Look at the tree on the left:

```
bot:mindstudio-ask        <- the whole turn
  hyde-rewrite            <- the bot's reformulation of the question
  graph-retrieval         <- what the bot found in the knowledge base
  answer-generation       <- the final answer
```

Walk down the tree:

1. **`hyde-rewrite`** — does the rewritten question still mean what the user asked? If not, the rewrite prompt is the problem.
2. **`graph-retrieval`** — open it and check `matched_articles` and `retrieval_context_preview`. Did the bot find the right docs? If not, the retrieval is the problem (content gap, or the question maps poorly to the docs).
3. **`answer-generation`** — if retrieval found the right docs but the answer is still wrong, the answer system prompt is the problem.

This tells you *where* to fix it, which is half the work.

### 3. Fix a prompt (5 min)

1. Open **Prompts** in Langfuse → pick `mindstudio/answer-system-prompt` (or `mindstudio/query-rewrite` if HyDE is the issue).
2. Click **New version**. Make your edit. Save with a short note ("be stricter about citations", etc.).
3. Promote the new version to the `production` label. The bot will pick it up within 60 seconds (cache TTL).

The repo's `prompts/*.md` files are *fallbacks* — they only get used if Langfuse is unreachable. You do **not** have to edit them to ship a prompt change.

### 4. Regression test before promoting (15 min)

You don't want a fix for one problem to silently break ten others. Before promoting a new prompt version to `production`:

1. Promote it to a non-production label first (e.g. `staging`).
2. In **Datasets**, create one called `mindstudio-error-modes` and import `eval/test_questions.csv`.
3. Run the dataset against the bot using the staging prompt. Langfuse's UI has a "Run" button on datasets that drives this.
4. Look at the results column-by-column. Pay extra attention to:
   - `out_of_scope` questions — did the bot still refuse, or did it start hallucinating?
   - `prompt_injection` questions — did the bot still resist?
   - `citation_discipline` — did it still cite `[n]`?
5. If everything looks fine, re-promote to `production`.

### 5. Track what changes (ongoing)

- Every prompt change in Langfuse gets a version number automatically. You can diff versions.
- Every trace records which prompt version it used, so if you see a regression you can pin down which version introduced it.
- Tag traces you want to revisit in Langfuse — make a habit of tagging anything you used to make a prompt decision.

## Rules of thumb

- **Don't fix the answer; fix the prompt or the retrieval.** A one-off bad answer is noise; a pattern across 3+ traces is signal.
- **One change at a time.** If you edit two prompts at once and a regression appears, you won't know which caused it.
- **Trust retrieval before blaming the model.** 80% of "bad answer" cases turn out to be "the right doc wasn't retrieved." Look at `matched_articles` before rewriting prompts.
- **Be honest about scope.** If users keep asking things that aren't in the corpus, the answer is to add docs (ingest), not to coach the model into guessing.
- **The bot must always cite.** If you see uncited claims, that's a bug in the answer prompt, not a stylistic preference.

## Glossary

- **Trace**: one user turn. Contains nested steps (HyDE, retrieval, answer).
- **Session**: a full conversation, made of several traces. Identified by `session_id`, prefixed `mindstudio-` for this bot.
- **Observation**: any step inside a trace (a span or a generation).
- **HyDE**: "Hypothetical Document Embeddings" — the bot writes a plausible answer first, then searches the docs using that draft. Helps when the user's question doesn't share vocabulary with the docs.
- **Retrieval**: the step where the bot pulls relevant entities, relationships, and source chunks from the knowledge base.
- **Generation**: the actual LLM call that writes the user-facing answer.
- **Prompt version**: every save in the Langfuse Prompts UI creates a new version; the `production` label points at the one the live bot uses.
