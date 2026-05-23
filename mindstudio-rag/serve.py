"""FastAPI server for the MindStudio RAG bot.

Retrieval = GraphRAG-style local search (Edge et al. 2024):
    1. HyDE: generate a hypothetical answer passage and embed it.
    2. Vector search over chunks (top-k).
    3. Vector search over entity descriptions (top-k).
    4. Pull entities mentioned in the top chunks (graph-aware expansion).
    5. Pull 1-hop relationships for the union of entities.
    6. Assemble ENTITIES + RELATIONSHIPS + SOURCES context block.
    7. Generate answer with [n] citations to SOURCES.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Load .env (overrides empty/missing values; preserves real shell values)
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if not os.environ.get(k):
                os.environ[k] = v

from anthropic import Anthropic  # noqa: E402

from ingest import communities as communities_mod  # noqa: E402
from ingest import embed as embed_mod  # noqa: E402
from ingest import store as store_mod  # noqa: E402
from langfuse_integration import (  # noqa: E402
    end_trace, extract_usage, flush, get_prompt, start_trace,
)

PROMPTS_DIR = ROOT / "prompts"
DB_PATH = ROOT / "store" / "corpus.db"

ANSWER_PROMPT_ID = "mindstudio/answer-system-prompt"
HYDE_PROMPT_ID = "mindstudio/query-rewrite"

ANSWER_MODEL = "claude-sonnet-4-6"
HYDE_MODEL = "claude-haiku-4-5-20251001"

K_CHUNKS = 12
K_ENTITIES = 8
TOP_PAGES = 5
REL_LIMIT = 30


def _fallback(name: str) -> str:
    p = PROMPTS_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


app = FastAPI(title="MindStudio RAG")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


class State:
    conn = None
    anthropic: Optional[Anthropic] = None


def _ensure_loaded() -> None:
    if State.conn is None:
        if not DB_PATH.exists():
            raise RuntimeError(f"corpus.db not found at {DB_PATH}. Run ingest/build.py first.")
        State.conn = store_mod.open_db(DB_PATH)
        State.anthropic = Anthropic()


# ── HyDE ───────────────────────────────────────────────────────────────────
def _format_history_for_hyde(history: Optional[list]) -> str:
    """Render the last few turns as plain text so HyDE can resolve references
    like 'the other one' or 'that block' before generating the hypothetical
    passage. Trimmed to keep the rewrite cheap."""
    if not history:
        return ""
    tail = list(history)[-4:]
    lines = [f"{h.role.capitalize()}: {h.content}" for h in tail]
    return "Recent conversation:\n" + "\n".join(lines) + "\n\n"


# Tokens that suggest the question refers back to something earlier in the
# conversation ("what about that one?"). When none are present and the
# question is reasonably specific, we skip HyDE to save ~0.5-1s per turn.
_REFERENCE_TOKENS = (
    " that ", " this ", " it ", " it?", " they ", " them ", " those ",
    " the other", " what about", " and ", " also", " too?", " hierover",
    " daarover", " die ", " dat ", " hij ", " zij ", " ze ",
)


def _hyde_would_help(question: str, history: Optional[list]) -> bool:
    """Return True when HyDE is worth its latency.

    Skipped when:
    - The question is long and specific (>= 60 chars) AND has no history AND
      contains no obvious back-references — in that case the literal question
      already embeds well.
    """
    if history:
        return True  # follow-ups frequently need reference resolution
    q = f" {question.lower().strip()} "
    if len(question) < 60:
        return True  # short questions benefit from HyDE vocabulary expansion
    if any(tok in q for tok in _REFERENCE_TOKENS):
        return True
    return False


def _hyde(question: str, history: Optional[list] = None, trace=None) -> str:
    fb = _fallback("query-rewrite.md")
    system, prompt_obj = get_prompt(HYDE_PROMPT_ID, fb)
    hist_block = _format_history_for_hyde(history)
    user_content = f"{hist_block}Current question: {question}" if hist_block else question
    messages = [{"role": "user", "content": user_content}]
    try:
        # HyDE only needs a short hypothetical passage; cap tokens low so the
        # rewrite step doesn't dominate time-to-first-token of the real answer.
        resp = State.anthropic.messages.create(
            model=HYDE_MODEL, max_tokens=160, system=system, messages=messages,
        )
        out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if trace is not None:
            trace.record_generation(
                model=HYDE_MODEL, messages=messages, system_prompt=system,
                output_text=out, usage=extract_usage(resp), prompt_obj=prompt_obj,
            )
        return out or question
    except Exception:
        return question


# ── Local search ───────────────────────────────────────────────────────────
def retrieve(question: str, history: Optional[list] = None, trace=None) -> dict:
    if _hyde_would_help(question, history):
        hyde_passage = _hyde(question, history=history, trace=trace)
        embed_text = f"{question}\n\n{hyde_passage}"
    else:
        hyde_passage = ""  # skipped — question is self-contained
        embed_text = question

    try:
        qvec = embed_mod.embed_query(embed_text)
    except Exception as e:
        print(f"[serve] embed_query failed: {e}", file=sys.stderr)
        return {"hyde": hyde_passage, "chunks": [], "entities": [], "relationships": [],
                "pages": [], "fallback": True}

    chunk_hits = store_mod.vector_search_chunks(State.conn, qvec, k=K_CHUNKS)
    entity_hits = store_mod.vector_search_entities(State.conn, qvec, k=K_ENTITIES)

    # Graph-aware expansion: entities mentioned in top chunks
    chunk_ids = [h["chunk_id"] for h in chunk_hits[:K_CHUNKS]]
    mentioned = store_mod.entities_for_chunks(State.conn, chunk_ids)

    entity_by_name: dict[str, dict] = {}
    for e in entity_hits + mentioned:
        entity_by_name.setdefault(e["name"], {
            "name": e["name"], "type": e["type"], "description": e["description"],
        })
    entity_names = list(entity_by_name.keys())

    relationships = store_mod.neighbour_relationships(State.conn, entity_names, limit=REL_LIMIT)
    collections = communities_mod.communities_for_entities(State.conn, entity_names)[:3]

    # Rank pages: vector hit (1/(1+dist)) + small bonus per linked entity
    page_scores: dict[str, float] = {}
    page_meta: dict[str, dict] = {}
    for h in chunk_hits:
        page_scores[h["url"]] = page_scores.get(h["url"], 0) + 1.0 / (1.0 + h["distance"])
        page_meta.setdefault(h["url"], {"title": h["title"], "summary": h["summary"]})
    # Pages where mentioned entities live also get a small bonus
    for r in relationships:
        doc = r.get("document")
        if doc:
            page_scores[doc] = page_scores.get(doc, 0) + 0.1 * (r["strength"] / 10.0)

    top_pages = sorted(page_scores.items(), key=lambda kv: kv[1], reverse=True)[:TOP_PAGES]

    # For each top page, pick the best (lowest-distance) chunks
    chunks_by_url: dict[str, list[dict]] = {}
    for h in chunk_hits:
        chunks_by_url.setdefault(h["url"], []).append(h)

    sources: list[dict] = []
    for url, score in top_pages:
        meta = page_meta.get(url)
        if meta is None:
            row = State.conn.execute("SELECT title, summary FROM pages WHERE url=?", (url,)).fetchone()
            if not row:
                continue
            meta = {"title": row[0], "summary": row[1]}
        chunks = chunks_by_url.get(url, [])[:2]
        if not chunks:
            row2 = State.conn.execute(
                "SELECT heading_path, text FROM chunks WHERE page_url=? LIMIT 2", (url,)
            ).fetchall()
            chunks = [{"heading_path": r[0], "text": r[1]} for r in row2]
        sources.append({
            "url": url, "title": meta["title"], "summary": meta["summary"],
            "score": round(score, 3),
            "chunks": [{"heading_path": c["heading_path"], "text": c["text"]} for c in chunks],
        })

    return {
        "hyde": hyde_passage,
        "chunks": [{"url": h["url"], "heading_path": h["heading_path"],
                    "distance": h["distance"]} for h in chunk_hits[:8]],
        "entities": list(entity_by_name.values()),
        "relationships": relationships,
        "collections": collections,
        "pages": [u for u, _ in top_pages],
        "sources": sources,
        "fallback": not bool(top_pages),
    }


def _format_context(retrieval: dict) -> str:
    """Build a GraphRAG-style context block: COLLECTIONS, ENTITIES, RELATIONSHIPS, SOURCES."""
    parts: list[str] = []

    if retrieval.get("collections"):
        lines = ["-----COLLECTIONS-----", "title | summary"]
        for c in retrieval["collections"]:
            summary = (c.get("summary") or "").replace("|", "/").replace("\n", " ")
            lines.append(f"{c['title']} | {summary}")
        parts.append("\n".join(lines))

    if retrieval["entities"]:
        lines = ["-----ENTITIES-----", "name | type | description"]
        for e in retrieval["entities"]:
            desc = (e.get("description") or "").replace("|", "/")
            lines.append(f"{e['name']} | {e['type']} | {desc}")
        parts.append("\n".join(lines))

    if retrieval["relationships"]:
        lines = ["-----RELATIONSHIPS-----", "source | target | description | strength"]
        for r in retrieval["relationships"]:
            desc = (r.get("description") or "").replace("|", "/")
            lines.append(f"{r['source']} | {r['target']} | {desc} | {r['strength']}")
        parts.append("\n".join(lines))

    if retrieval["sources"]:
        lines = ["-----SOURCES-----"]
        for i, s in enumerate(retrieval["sources"], 1):
            chunk_text = "\n\n".join(c["text"] for c in s["chunks"])
            lines.append(f"[{i}] {s['title']}\nURL: {s['url']}\nSummary: {s['summary']}\n\n{chunk_text}")
        parts.append("\n\n".join(lines))

    return "\n\n".join(parts) if parts else "(no documents found)"


# ── API ────────────────────────────────────────────────────────────────────
class HistoryItem(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AskRequest(BaseModel):
    question: str
    history: Optional[list[HistoryItem]] = None
    session_id: Optional[str] = None


@app.get("/api/health")
def health():
    try:
        _ensure_loaded()
        return {"ok": True, **store_mod.stats(State.conn)}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/api/collections")
def collections():
    _ensure_loaded()
    return {"collections": communities_mod.list_all(State.conn)}


@app.get("/api/graph-data")
def graph_data():
    """Single payload for the UI graph view: entities + relationships + community map."""
    _ensure_loaded()
    entities = [
        {"id": r[0], "name": r[1], "type": r[2], "description": r[3]}
        for r in State.conn.execute(
            "SELECT id, name, type, description FROM entities"
        ).fetchall()
    ]
    relationships = [
        {"source": r[0], "target": r[1], "description": r[2], "strength": r[3]}
        for r in State.conn.execute(
            "SELECT source_name, target_name, description, strength FROM relationships"
        ).fetchall()
    ]
    communities = [
        {"id": r[0], "title": r[1], "size": r[2]}
        for r in State.conn.execute(
            "SELECT id, title, size FROM communities ORDER BY size DESC"
        ).fetchall()
    ]
    members = [
        {"community_id": r[0], "entity_name": r[1]}
        for r in State.conn.execute(
            "SELECT community_id, entity_name FROM community_members"
        ).fetchall()
    ]
    degree: dict[str, int] = {}
    for r in relationships:
        degree[r["source"]] = degree.get(r["source"], 0) + 1
        degree[r["target"]] = degree.get(r["target"], 0) + 1
    for e in entities:
        e["degree"] = degree.get(e["name"], 0)

    return {
        "entities": entities,
        "relationships": relationships,
        "communities": communities,
        "members": members,
    }


@app.get("/api/graph")
def graph():
    _ensure_loaded()
    entities = [
        {"id": r[0], "name": r[1], "type": r[2], "description": r[3], "source_url": r[4]}
        for r in State.conn.execute(
            "SELECT id, name, type, description, source_url FROM entities"
        ).fetchall()
    ]
    relationships = [
        {"source": r[0], "target": r[1], "description": r[2],
         "strength": r[3], "document": r[4]}
        for r in State.conn.execute(
            "SELECT source_name, target_name, description, strength, document_url FROM relationships"
        ).fetchall()
    ]
    return {"entities": entities, "relationships": relationships}


@app.post("/api/ask")
def ask(req: AskRequest):
    _ensure_loaded()
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(400, "question is required")
    if len(question) > 500:
        raise HTTPException(400, "question too long")

    # Prefix the session_id with the bot name so conversation designers can
    # tell mindstudio sessions apart from other bots at a glance in the
    # Langfuse Sessions list. MindStudio supplies its own session id per
    # conversation; if it isn't passed, fall back to a timestamp.
    raw_session_id = req.session_id or f"sess-{int(time.time())}"
    session_id = raw_session_id if raw_session_id.startswith("mindstudio-") else f"mindstudio-{raw_session_id}"
    trace = start_trace(
        name="bot:mindstudio-ask",
        session_id=session_id,
        input_text=question,
        metadata={"source": "mindstudio", "question": question},
        tags=["mindstudio", "ask"],
    )

    try:
        retrieval = retrieve(question, history=req.history, trace=trace)
        try:
            trace.record_retrieval(question, {
                "matched_articles": retrieval["pages"],
                "matched_topics": [e["name"] for e in retrieval["entities"]],
                "fired_triples": retrieval["relationships"][:20],
                "matched_themes": [],
                "fallback": retrieval["fallback"],
                "hyde": retrieval["hyde"],
            })
        except Exception:
            pass

        context = _format_context(retrieval)
        system, prompt_obj = get_prompt(ANSWER_PROMPT_ID, _fallback("answer-system-prompt.md"))
        user = f"---User question---\n{question}\n\n---Data---\n{context}"

        # Build the conversation: prior turns verbatim, then the new user
        # turn with retrieval context attached. Assistant prior turns are
        # passed as-is so the model can refer back to them naturally.
        messages: list[dict] = []
        if req.history:
            for h in req.history:
                if h.role in ("user", "assistant") and h.content:
                    messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": user})

        # Mark the system prompt as cacheable. Anthropic's prompt cache returns
        # the answer faster (and cheaper) when the same system prompt is reused
        # across requests — which is the common case here.
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        source_urls = [s["url"] for s in retrieval["sources"]]

        def stream():
            collected: list[str] = []
            yield json.dumps({"type": "sources", "sources": [
                {"n": i + 1, "url": s["url"], "title": s["title"], "score": s["score"]}
                for i, s in enumerate(retrieval["sources"])
            ]}) + "\n"
            final_msg = None
            try:
                with State.anthropic.messages.stream(
                    model=ANSWER_MODEL, max_tokens=900, system=system_blocks, messages=messages,
                ) as stream_resp:
                    for text in stream_resp.text_stream:
                        collected.append(text)
                        yield json.dumps({"type": "token", "text": text}) + "\n"
                    final_msg = stream_resp.get_final_message()
            except Exception as e:
                yield json.dumps({"type": "error", "error": str(e)}) + "\n"
                trace.set_error(str(e))
                return
            answer = "".join(collected)
            try:
                trace.record_generation(
                    model=ANSWER_MODEL, messages=messages, system_prompt=system,
                    output_text=answer, usage=extract_usage(final_msg), prompt_obj=prompt_obj,
                )
            except Exception:
                pass
            trace.set_output(answer)
            # Surface the key fields as trace-level metadata so conversation
            # designers can read / filter them as variables in Langfuse.
            try:
                trace.set_metadata({
                    # Inputs / outputs
                    "question": question,
                    "answer": answer,
                    # Intermediate prompt outputs (promoted to trace-level
                    # variables so designers don't have to drill into child
                    # observations to see them).
                    "hyde_rewrite": retrieval.get("hyde", "") or "(skipped)",
                    "matched_articles": retrieval.get("pages", []),
                    "matched_topics": [e["name"] for e in retrieval.get("entities", [])],
                    "fired_triples_count": len(retrieval.get("relationships", [])),
                    "retrieval_context_preview": context[:1500],
                    # Sources + run info
                    "num_sources": len(source_urls),
                    "source_urls": source_urls,
                    "fallback": retrieval.get("fallback", False),
                    "answer_model": ANSWER_MODEL,
                    "history_turns": len(req.history or []),
                })
            except Exception:
                pass
            yield json.dumps({"type": "done"}) + "\n"

        def stream_and_close():
            try:
                yield from stream()
            finally:
                end_trace(trace)
                flush()

        return StreamingResponse(stream_and_close(), media_type="application/x-ndjson")
    except Exception as e:
        trace.set_error(str(e))
        end_trace(trace)
        flush()
        raise HTTPException(500, str(e))
