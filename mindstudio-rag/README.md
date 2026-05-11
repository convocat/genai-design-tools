# MindStudio University RAG bot

Graph-RAG chatbot over `https://university.mindstudio.ai/`. Microsoft GraphRAG-style entity + relationship extraction, Louvain community detection, HyDE query rewriting, hybrid vector + graph retrieval. Local SQLite + sqlite-vec, Langfuse-managed prompts.

See [GRAPHRAG.md](./GRAPHRAG.md) for the architecture deep dive.

## Layout

```
ingest/        crawl → parse → chunk → summarize → extract-graph → embed → communities
prompts/       5 markdown prompts (Langfuse is the runtime source of truth; these are fallbacks)
store/         corpus.db (SQLite + sqlite-vec) + graph.json
serve.py       FastAPI app: /api/ask (streaming), /api/graph, /api/collections, /api/health
api/index.py   Vercel serverless entry point
ui/            React + Vite + Tailwind + assistant-ui + react-force-graph-2d
vercel.json    deploy config
```

## Setup (local)

```
python -m venv .venv
.venv\Scripts\activate                    # Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                    # fill ANTHROPIC_API_KEY, OPENAI_API_KEY, LANGFUSE_*

cd ui && npm install && cd ..
```

## Run (local)

```
# Ingest (one-shot, ~$1–2 in LLM costs)
python ingest/build.py --dry-run         # plan + cost estimate
python ingest/build.py                   # full crawl + extract + embed + community detect

# Push prompts to Langfuse
python sync_prompts_to_langfuse.py

# Start API + UI (two terminals)
python -m uvicorn serve:app --port 8790
cd ui && npm run dev                     # http://localhost:5173
```

## API

| Method | Path | Returns |
|---|---|---|
| POST | `/api/ask` | streaming ndjson: `sources` → `token`* → `done` |
| GET | `/api/health` | `{ pages, chunks, entities, relationships }` |
| GET | `/api/collections` | the 33 smart collections with titles + summaries |
| GET | `/api/graph` | all entities + relationships |
| GET | `/api/graph-data` | entities + relationships + communities + community memberships (used by the UI graph tab) |

## Deploy (Vercel)

The repo deploys as one Vercel project: the Python FastAPI app handles `/api/*` via the serverless function, the Vite UI is served statically from `ui/dist/`.

1. Push this repo to GitHub.
2. New project in Vercel → import the repo.
3. Set env vars in the Vercel dashboard:
   - `ANTHROPIC_API_KEY`
   - `OPENAI_API_KEY`
   - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
4. Build/output paths are already set in `vercel.json`. Deploy.

### Production notes

- **`corpus.db` ships in the repo** (22 MB). When ingest outgrows GitHub's 100 MB single-file limit, move it to Vercel Blob and download into `/tmp` on cold start.
- **Cost per question**: ~$0.01–0.03 (HyDE Haiku + answer Sonnet + one embedding call). Public deploy without rate limiting is fine for low traffic but watch the dashboard.
- **CORS** is wide open. If the bot is embedded only at `maaike.ai`, narrow `allow_origins` in `serve.py` before going prod.
- **Cold start**: the FastAPI module loads sqlite-vec and opens the DB on first request (~1–2 s). Subsequent requests reuse the module.

## Cost guardrails

- Ingest is manual (`python ingest/build.py`) — never call from cron / CI.
- Query-time costs scale with traffic; consider a per-IP rate limit (todo).
- Langfuse traces every prompt + generation so you can pivot by cost in their UI.
