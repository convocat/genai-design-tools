"""Smart collections via community detection on the entity graph.

Implements the GraphRAG "global" component (simplified):
    1. Build a weighted entity graph from relationships (weight = strength).
    2. Detect communities with NetworkX Louvain (greedy modularity fallback).
    3. For each community, ask an LLM to produce a title + summary.
    4. Persist communities + members to SQLite.

The full Microsoft GraphRAG paper uses hierarchical Leiden; we use Louvain
because it ships with NetworkX and avoids heavy native deps. The output
shape matches: { id, level, title, summary, members: [entity_name] }.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Iterable

# networkx is only needed at ingest (community detection); serve.py imports
# this module for SQL-only helpers (list_all, communities_for_entities) and
# must not pull a 30+ MB dependency into the serverless bundle. Lazy import
# inside the functions that need it.
# import networkx as nx  -- moved into _build_graph / _detect

# anthropic + langfuse helpers are only used by summarize_community +
# detect_and_summarize (ingest paths). Lazy-import to keep the runtime bundle lean.
# from anthropic import Anthropic
# from langfuse_integration import end_trace, extract_usage, get_prompt, start_trace

MODEL = "claude-haiku-4-5-20251001"
PROMPT_ID = "mindstudio/summarize-community"
MIN_COMMUNITY_SIZE = 3
MAX_ENTITIES_IN_PROMPT = 25
MAX_RELS_IN_PROMPT = 30


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS communities (
        id INTEGER PRIMARY KEY,
        level INTEGER,
        title TEXT,
        summary TEXT,
        size INTEGER
    );
    CREATE TABLE IF NOT EXISTS community_members (
        community_id INTEGER,
        entity_name TEXT,
        PRIMARY KEY (community_id, entity_name)
    );
    CREATE INDEX IF NOT EXISTS idx_cm_entity ON community_members(entity_name);
    """)
    conn.commit()


def _build_graph(conn: sqlite3.Connection):
    import networkx as nx
    g = nx.Graph()
    for row in conn.execute("SELECT name FROM entities").fetchall():
        g.add_node(row[0])
    for r in conn.execute(
        "SELECT source_name, target_name, strength FROM relationships"
    ).fetchall():
        s, t, w = r[0], r[1], int(r[2] or 1)
        if g.has_edge(s, t):
            g[s][t]["weight"] += w
        else:
            g.add_edge(s, t, weight=w)
    return g


def _detect(g) -> list[set[str]]:
    import networkx as nx
    if g.number_of_nodes() == 0:
        return []
    try:
        comms = nx.community.louvain_communities(g, weight="weight", seed=7)
    except Exception:
        comms = list(nx.community.greedy_modularity_communities(g, weight="weight"))
    return [set(c) for c in comms]


def _community_payload(conn: sqlite3.Connection, members: set[str]) -> dict:
    qs = ",".join("?" * len(members))
    ents = conn.execute(
        f"SELECT name, type, description FROM entities WHERE name IN ({qs})",
        list(members),
    ).fetchall()
    rels = conn.execute(
        f"""
        SELECT source_name, target_name, description, strength
        FROM relationships
        WHERE source_name IN ({qs}) AND target_name IN ({qs})
        ORDER BY strength DESC
        LIMIT ?
        """,
        list(members) + list(members) + [MAX_RELS_IN_PROMPT],
    ).fetchall()
    return {
        "entities": [{"name": r[0], "type": r[1], "description": r[2]} for r in ents[:MAX_ENTITIES_IN_PROMPT]],
        "relationships": [
            {"source": r[0], "target": r[1], "description": r[2], "strength": r[3]}
            for r in rels
        ],
    }


def _format_for_prompt(payload: dict) -> str:
    parts = ["ENTITIES (name | type | description):"]
    for e in payload["entities"]:
        parts.append(f"  {e['name']} | {e['type']} | {e['description']}")
    parts.append("")
    parts.append("RELATIONSHIPS (source -> target | description | strength):")
    for r in payload["relationships"]:
        parts.append(f"  {r['source']} -> {r['target']} | {r['description']} | {r['strength']}")
    return "\n".join(parts)


def summarize_community(client, payload: dict, fallback_text: str,
                        trace=None) -> tuple[str, str]:
    from langfuse_integration import extract_usage, get_prompt
    system, prompt_obj = get_prompt(PROMPT_ID, fallback_text)
    user = _format_for_prompt(payload)
    messages = [{"role": "user", "content": user}]
    resp = client.messages.create(
        model=MODEL, max_tokens=400, system=system, messages=messages,
    )
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()

    if trace is not None:
        try:
            trace.record_generation(
                model=MODEL, messages=messages, system_prompt=system,
                output_text=raw, usage=extract_usage(resp), prompt_obj=prompt_obj,
            )
        except Exception:
            pass

    try:
        data = json.loads(raw)
        return str(data.get("title") or "Untitled cluster"), str(data.get("summary") or "")
    except Exception:
        return "Untitled cluster", raw[:400]


def detect_and_summarize(conn: sqlite3.Connection, fallback_text: str,
                         progress=print) -> int:
    """Replace any existing communities with freshly detected ones."""
    from anthropic import Anthropic
    from langfuse_integration import end_trace, start_trace

    init_schema(conn)
    conn.execute("DELETE FROM communities")
    conn.execute("DELETE FROM community_members")

    g = _build_graph(conn)
    progress(f"[communities] graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
    comms = _detect(g)
    comms = [c for c in comms if len(c) >= MIN_COMMUNITY_SIZE]
    progress(f"[communities] {len(comms)} community(ies) >= {MIN_COMMUNITY_SIZE} entities")

    if not comms:
        return 0

    client = Anthropic()
    written = 0
    for i, members in enumerate(sorted(comms, key=len, reverse=True)):
        payload = _community_payload(conn, members)
        trace = start_trace(
            name="ingest:community-summary",
            input_text=f"community {i} ({len(members)} entities)",
            metadata={"size": len(members)},
            tags=["ingest", "mindstudio", "community"],
        )
        try:
            title, summary = summarize_community(client, payload, fallback_text, trace=trace)
            cur = conn.execute(
                "INSERT INTO communities(level, title, summary, size) VALUES (?, ?, ?, ?)",
                (0, title, summary, len(members)),
            )
            cid = cur.lastrowid
            for name in members:
                conn.execute(
                    "INSERT INTO community_members(community_id, entity_name) VALUES (?, ?)",
                    (cid, name),
                )
            conn.commit()
            written += 1
            progress(f"[communities] {i+1:>2}. [{len(members):>3}] {title}")
            trace.set_output(f"{title} :: {len(members)} entities")
        except Exception as e:
            progress(f"[communities] ! {e}")
            trace.set_error(str(e))
        finally:
            end_trace(trace)
    return written


def list_all(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, level, title, summary, size FROM communities ORDER BY size DESC"
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        members = [m[0] for m in conn.execute(
            "SELECT entity_name FROM community_members WHERE community_id=?", (r[0],)
        ).fetchall()]
        out.append({
            "id": r[0], "level": r[1], "title": r[2], "summary": r[3],
            "size": r[4], "members": members,
        })
    return out


def communities_for_entities(conn: sqlite3.Connection, names: Iterable[str]) -> list[dict]:
    names = list(names)
    if not names:
        return []
    qs = ",".join("?" * len(names))
    rows = conn.execute(
        f"""
        SELECT DISTINCT c.id, c.title, c.summary, c.size
        FROM communities c
        JOIN community_members cm ON cm.community_id = c.id
        WHERE cm.entity_name IN ({qs})
        ORDER BY c.size DESC
        """,
        names,
    ).fetchall()
    return [{"id": r[0], "title": r[1], "summary": r[2], "size": r[3]} for r in rows]
