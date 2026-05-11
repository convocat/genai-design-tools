# MindStudio University RAG bot

Graph + vector RAG over `https://university.mindstudio.ai/`. One-shot ingest. Local SQLite + sqlite-vec store. Langfuse for prompts and traces.

## Layout

```
ingest/        crawl → parse → chunk → summarize → extract-graph → embed → write
prompts/       4 markdown prompts (fallbacks; source of truth is Langfuse after sync)
store/         corpus.db (SQLite + sqlite-vec) + graph.json
serve.py       FastAPI app: /api/ask (streaming), /api/graph, /api/health
langfuse_integration.py   imports karpathy-wiki helpers
sync_prompts_to_langfuse.py
```

## Setup

```
cd tools/mindstudio-rag
python -m venv .venv
.venv\Scripts\activate         # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # then fill ANTHROPIC_API_KEY, VOYAGE_API_KEY, LANGFUSE_*
```

## Run

```
# 1. Dry-run the crawl plan
python ingest/build.py --dry-run

# 2. Full ingest (one-shot, ~$1-2 in API costs)
python ingest/build.py

# 3. Sync prompts to Langfuse
python sync_prompts_to_langfuse.py --dry-run
python sync_prompts_to_langfuse.py

# 4. Serve
uvicorn serve:app --port 8790 --reload
```

## API

- `POST /api/ask` — `{ "question": "..." }` → streaming JSON-lines (tokens + sources)
- `GET /api/graph` — nodes + edges
- `GET /api/health` — store stats
