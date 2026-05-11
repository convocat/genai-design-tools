# GraphRAG: a short build manual

A practical introduction to graph-based retrieval-augmented generation, written in the context of this MindStudio docs bot. Read this first if you are new to GraphRAG, or use it as a map when extending the tool.

## What is GraphRAG?

Plain RAG retrieves *chunks of text* by embedding similarity and stuffs them into a prompt. It works, but it has known weaknesses:

- It cannot answer **broad questions** ("what are the main themes of this corpus?") because no single chunk contains the answer.
- It treats each chunk as independent, so it misses relationships **across documents** ("X is a special case of Y, defined in another file").
- It wastes context on near-duplicate chunks because vector search has no notion of *information*, only similarity.

GraphRAG (Microsoft Research, [Edge et al. 2024](https://arxiv.org/abs/2404.16130)) addresses this by building an **entity-relationship graph** over the corpus during ingest, then using that graph at query time to assemble a richer context.

Two query modes:

- **Local search** — answer specific questions. Vector-retrieve chunks, find entities mentioned in those chunks, expand to neighbours via relationships, return ENTITIES + RELATIONSHIPS + SOURCES as the prompt context.
- **Global search** — answer broad questions. Cluster the entity graph into communities, generate an LLM summary per community, route the question against community summaries.

## Pipeline overview

```
                  ┌────────────────────── INGEST ──────────────────────┐
                  │                                                    │
crawl → parse → chunk ──► embed ──► vector index (chunks)              │
                  │                                                    │
                  ├──► LLM extract ──► entities, relationships ──► graph
                  │       (per page)                                   │
                  │                                                    │
                  └──► community detection ──► LLM summarise ──► collections
                                                                       │
                                                                       ▼
                  ┌────────────────────── QUERY ───────────────────────┐
                  │                                                    │
question ──► HyDE ──► embed ──► vector hits (chunks + entities)        │
                                          │                            │
                                          ▼                            │
                                graph expansion (1-hop)                │
                                          │                            │
                                          ▼                            │
                       prompt: COLLECTIONS + ENTITIES + RELS + SOURCES │
                                          │                            │
                                          ▼                            │
                                       answer + [n] citations          │
                                                                       │
                  └────────────────────────────────────────────────────┘
```

## Ingest, step by step

1. **Crawl** the source (`ingest/crawl.py`). Same-host BFS, `httpx + selectolax`, sitemap-aware.
2. **Parse + clean** (`ingest/parse.py`). Drop nav, footer, scripts; convert `<main>` to markdown via `markdownify`.
3. **Chunk** (`ingest/chunk.py`). Heading-aware, ~600 tokens, 80-token overlap. Each chunk knows its `heading_path`.
4. **Summarise the page** (`ingest/summarize.py`, prompt `mindstudio/summarize-page`). One sentence used in the SOURCES block at query time.
5. **Extract entities + relationships** (`ingest/extract_graph.py`, prompt `mindstudio/extract-graph`). One LLM call per page. The model returns:
   ```json
   {
     "entities":      [{"name": "...", "type": "...", "description": "..."}],
     "relationships": [{"source": "...", "target": "...", "description": "...", "strength": 7}]
   }
   ```
   Open vocabulary on names and descriptions; `type` is from a small enum; `strength` is 1-10. This is the [Microsoft GraphRAG schema](https://github.com/microsoft/graphrag/blob/main/graphrag/prompts/index/extract_graph.py).
6. **Embed** (`ingest/embed.py`). Two vector spaces:
   - chunk text → `vec_chunks`
   - entity description (formatted as `name (type): description`) → `vec_entities`
7. **Persist** (`ingest/store.py`). SQLite + sqlite-vec. Chunks have a mention table linking them to the entities they reference.
8. **Smart collections** (`ingest/communities.py`, prompt `mindstudio/summarize-community`). Build the entity graph weighted by relationship `strength`, run NetworkX **Louvain community detection**, drop communities under 3 entities, ask the LLM for a `title` + `summary` per community. This is a lightweight version of the GraphRAG hierarchical Leiden + community-report pipeline; the full version adds multiple levels of granularity.

Trade-off note: production GraphRAG uses Leiden via `graspologic`; we use Louvain because it ships with NetworkX and avoids native dependencies. Quality is comparable for small/medium corpora.

## Query, step by step

For each `/api/ask` (`serve.py`):

1. **HyDE** (prompt `mindstudio/query-rewrite`). The LLM generates a hypothetical answer passage. We embed `question + hypothetical` together. Why: real docs match the *form of an answer* better than the *form of a question* ([Gao et al. 2022](https://arxiv.org/abs/2212.10496)).
2. **Vector search × 2**: top-k over chunks, top-k over entity descriptions.
3. **Graph expansion**: pull entities that are *mentioned* in the top chunks (the chunk-entity link table). Union with vector-hit entities.
4. **Neighbourhood**: load the top relationships (by strength) where either endpoint is in the entity union, capped at 30.
5. **Collections lookup**: which communities do these entities belong to? Take the top 3 by size.
6. **Rank pages**: `1 / (1 + chunk_distance)` per chunk hit, plus a small bonus per relationship sourced from the page. Top 5 pages become SOURCES.
7. **Assemble context**: `COLLECTIONS | ENTITIES | RELATIONSHIPS | SOURCES` as a structured block in the user message. Pipe-separated rows are easy for the model to parse and survive long-context attention better than nested JSON.
8. **Generate** with `mindstudio/answer-system-prompt`. The system prompt requires `[n]` citations to SOURCES.

## Why two embedding spaces?

A factual question like "what does the Iterate block do?" matches a chunk well. A relational question like "which features depend on data sources?" matches *entity descriptions* better than any single chunk. By searching both and unioning the entity set before graph expansion, we get the recall of vector search and the precision of graph traversal.

## Langfuse instrumentation

Every prompt is pulled from Langfuse with a 60-second TTL cache (`langfuse_integration.get_prompt`). Edit prompts in the Langfuse UI; the in-repo `prompts/*.md` files are fallbacks only.

Trace shapes:

- `bot:mindstudio-ask` per user question. Spans: `retrieval` (matched entities, relationships, hyde passage, fallback flag) and `generation` (linked to the Langfuse `answer-system-prompt` version).
- `ingest:page` per page during build. Spans: `summarize-page` generation, `extract-graph` generation.
- `ingest:community-summary` per community. Span: `summarize-community` generation.

Add a new prompt:

1. Drop `prompts/<name>.md`.
2. Add a tuple to `PROMPTS` in `sync_prompts_to_langfuse.py`.
3. Run `python sync_prompts_to_langfuse.py`.
4. Read it in code with `get_prompt("mindstudio/<name>", fallback_text)`.

## Extending the tool

| You want to | Touch |
|---|---|
| Crawl a different site | `ingest/crawl.py` (filter rules) and `MINDSTUDIO_BASE_URL` in `.env` |
| Try a different embedding model | `ingest/embed.py`, `DIM` constant in `ingest/store.py`. Re-ingest from scratch. |
| Add reranking | Insert between vector search and final ranking in `serve.retrieve`. Cohere Rerank or a cross-encoder is standard. |
| Add multi-hop reasoning | Iterate the graph expansion step: take the relationship endpoints, fetch *their* relationships, until a depth bound. |
| Add hierarchical communities | Run Louvain recursively on each community's subgraph. Store `level` on the community row (already in the schema). |
| Switch to a real graph DB | Replace `ingest/store.py` graph functions with Neo4j or Kuzu. Keep the chunks/embeddings in SQLite or move them too. |
| Evaluate quality | Add `eval.py` modelled on `tools/karpathy-wiki/tools/eval.py` with a 20-question golden set. |

## Glossary

- **Chunk**: a 400-700 token slice of source text with a heading path.
- **Entity**: a named thing in the corpus with a type and description. Comparable to a *node*.
- **Relationship**: a typed-by-description edge between two entities, weighted by `strength`.
- **HyDE**: Hypothetical Document Embeddings. Embed a fake answer instead of the question.
- **Local search**: answering a specific question using vector + graph expansion. Default mode here.
- **Global search**: answering a broad question using community summaries. We expose communities via `/api/collections` but do not yet route to "global mode" automatically.
- **Community / collection**: a cluster of densely connected entities, with an LLM-generated title and summary.
- **Louvain / Leiden**: graph community-detection algorithms. Leiden is the GraphRAG default; we use Louvain.

## Further reading

- Edge et al., *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*, 2024. https://arxiv.org/abs/2404.16130
- Microsoft GraphRAG repository. https://github.com/microsoft/graphrag
- Gao et al., *Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)*, 2022. https://arxiv.org/abs/2212.10496
- LangChain `LLMGraphTransformer`. https://python.langchain.com/docs/how_to/graph_constructing/
- LlamaIndex `PropertyGraphIndex`. https://docs.llamaindex.ai/en/stable/module_guides/indexing/lpg_index_guide/
