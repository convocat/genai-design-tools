"""One-shot ingest orchestrator (GraphRAG-style).

Pipeline per page:
    crawl -> parse -> chunk -> summarize -> extract entities/relationships
          -> embed (chunks + entity descriptions) -> persist + link mentions

Run:
    python ingest/build.py --dry-run     # plan only
    python ingest/build.py               # full ingest
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
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

from ingest import chunk as chunk_mod  # noqa: E402
from ingest import communities as communities_mod  # noqa: E402
from ingest import crawl as crawl_mod  # noqa: E402
from ingest import embed as embed_mod  # noqa: E402
from ingest import extract_graph as extract_mod  # noqa: E402
from ingest import parse as parse_mod  # noqa: E402
from ingest import store as store_mod  # noqa: E402
from ingest import summarize as summarize_mod  # noqa: E402
from langfuse_integration import end_trace, flush, start_trace  # noqa: E402

PROMPTS_DIR = ROOT / "prompts"
STORE_DIR = ROOT / "store"
DB_PATH = STORE_DIR / "corpus.db"
GRAPH_PATH = STORE_DIR / "graph.json"


def _slug_from_url(url: str) -> str:
    p = urlparse(url).path.strip("/") or "index"
    return re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-")[:80]


def _fallback(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _find_mentions(chunk_text: str, entity_names: list[str]) -> list[str]:
    """Return entity names whose token appears in the chunk text (case-insensitive)."""
    if not entity_names:
        return []
    lower = chunk_text.lower()
    return [n for n in entity_names if n.lower() in lower]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--base-url", default=os.environ.get("MINDSTUDIO_BASE_URL", "https://university.mindstudio.ai/"))
    ap.add_argument("--max-pages", type=int, default=int(os.environ.get("MINDSTUDIO_MAX_PAGES", "500")))
    ap.add_argument("--limit", type=int, default=0, help="Process only N pages (smoke test)")
    args = ap.parse_args()

    base_host = urlparse(args.base_url).hostname or ""
    print(f"[build] base_url={args.base_url}  max_pages={args.max_pages}  dry_run={args.dry_run}")

    # 1. Crawl
    pages = crawl_mod.crawl(args.base_url, max_pages=args.max_pages)
    print(f"[build] crawled {len(pages)} pages")
    if args.limit:
        pages = pages[: args.limit]
        print(f"[build] limited to {len(pages)} pages")

    # 2. Parse + chunk
    parsed: list[dict] = []
    all_chunks_count = 0
    total_tokens = 0
    for url, html in pages:
        rec = parse_mod.parse_page(url, html, base_host)
        if not rec["markdown"]:
            continue
        rec["chunks"] = chunk_mod.chunk_markdown(rec["url"], rec["title"], rec["markdown"])
        parsed.append(rec)
        all_chunks_count += len(rec["chunks"])
        total_tokens += sum(c["token_count"] for c in rec["chunks"])
    print(f"[build] parsed {len(parsed)} pages -> {all_chunks_count} chunks, {total_tokens:,} tokens")

    # Cost estimate (rough): Haiku in ~$1/Mtok, out ~$5/Mtok; Voyage ~$0.02/Mtok.
    est_haiku_in = total_tokens * 2 / 1_000_000
    est_haiku_out = len(parsed) * 0.0025  # summarize + extract output
    est_embed_chunks = total_tokens * 0.02 / 1_000_000
    est_embed_entities = len(parsed) * 5 * 50 * 0.02 / 1_000_000  # ~5 entities x ~50 tok each
    est = est_haiku_in + est_haiku_out + est_embed_chunks + est_embed_entities
    print(f"[build] est cost: ~${est:.2f}")

    if args.dry_run:
        print("[build] dry run, exiting")
        return 0

    # 3. Storage
    conn = store_mod.open_db(DB_PATH)
    store_mod.init_schema(conn)

    # 4. LLM passes + embed
    anthropic_client = Anthropic()
    summary_fb = _fallback("summarize-page.md")
    extract_fb = _fallback("extract-graph.md")
    now = datetime.now(timezone.utc).isoformat()

    for i, rec in enumerate(parsed, 1):
        url = rec["url"]
        title = rec["title"]
        markdown = rec["markdown"]
        chunks = rec["chunks"]
        print(f"[build] {i}/{len(parsed)} {url}  ({len(chunks)} chunks)")

        trace = start_trace(
            name="ingest:page",
            session_id=f"ingest-{int(time.time())}",
            input_text=url,
            metadata={"url": url, "title": title, "chunks": len(chunks)},
            tags=["ingest", "mindstudio"],
        )
        try:
            summary = summarize_mod.summarize_page(
                anthropic_client, title, markdown, summary_fb, trace=trace,
            )
            graph_data = extract_mod.extract_graph(
                anthropic_client, url, title, markdown, extract_fb, trace=trace,
            )

            # embed chunks
            chunk_texts = [c["text"] for c in chunks]
            chunk_embeds = embed_mod.embed_texts(chunk_texts) if chunk_texts else []

            # embed entity descriptions ("name: description" format, GraphRAG convention)
            ent_texts = [
                f"{e['name']} ({e['type']}): {e['description']}"
                for e in graph_data["entities"]
            ]
            ent_embeds = embed_mod.embed_texts(ent_texts) if ent_texts else []

            store_mod.upsert_page(
                conn, url=url, title=title, slug=_slug_from_url(url),
                summary=summary, markdown=markdown, ingested_at=now,
            )
            chunk_ids = store_mod.replace_chunks(conn, url, chunks, chunk_embeds)

            # entities + relationships
            name_to_id: dict[str, int] = {}
            for ent, emb in zip(graph_data["entities"], ent_embeds):
                eid = store_mod.upsert_entity(
                    conn, name=ent["name"], type_=ent["type"],
                    description=ent["description"], source_url=url, embedding=emb,
                )
                name_to_id[ent["name"]] = eid
            for rel in graph_data["relationships"]:
                store_mod.insert_relationship(
                    conn,
                    source=rel["source"], target=rel["target"],
                    description=rel["description"], strength=rel["strength"],
                    document_url=url,
                )

            # link chunk -> entity mentions (substring match)
            entity_names = list(name_to_id.keys())
            for cid, ch in zip(chunk_ids, chunks):
                mentioned = _find_mentions(ch["text"], entity_names)
                store_mod.link_chunk_entities(conn, cid, [name_to_id[n] for n in mentioned])

            conn.commit()
            trace.set_output(
                f"ok: {len(chunks)} chunks, {len(graph_data['entities'])} entities, "
                f"{len(graph_data['relationships'])} relationships"
            )
        except Exception as e:
            print(f"[build] ! {url}: {e}")
            trace.set_error(str(e))
        finally:
            end_trace(trace)

    store_mod.export_graph(conn, GRAPH_PATH)

    # 5. Smart collections (community detection + LLM summaries)
    print("[build] detecting smart collections...")
    community_fb = _fallback("summarize-community.md")
    n_comm = communities_mod.detect_and_summarize(conn, community_fb)
    print(f"[build] wrote {n_comm} smart collection(s)")

    s = store_mod.stats(conn)
    s["communities"] = n_comm
    print(f"[build] done. {s}")
    flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
