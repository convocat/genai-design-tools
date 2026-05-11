"""SQLite + sqlite-vec persistence (GraphRAG-style schema).

Tables:
    pages         (url, title, slug, summary, markdown, ingested_at)
    chunks        (id, page_url, heading_path, text, token_count)
    vec_chunks    (chunk_id, embedding)            -- sqlite-vec virtual
    entities      (id, name, type, description, source_url)
    vec_entities  (entity_id, embedding)           -- sqlite-vec virtual
    relationships (id, source_name, target_name, description, strength, document_url)
    chunk_entities(chunk_id, entity_id)            -- mention edges
"""
from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

import sqlite_vec

DIM = 1536


def open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
    CREATE TABLE IF NOT EXISTS pages (
        url TEXT PRIMARY KEY,
        title TEXT,
        slug TEXT,
        summary TEXT,
        markdown TEXT,
        ingested_at TEXT
    );
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        page_url TEXT,
        heading_path TEXT,
        text TEXT,
        token_count INTEGER,
        FOREIGN KEY (page_url) REFERENCES pages(url) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(page_url);
    CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(
        chunk_id INTEGER PRIMARY KEY,
        embedding FLOAT[{DIM}]
    );

    CREATE TABLE IF NOT EXISTS entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        type TEXT,
        description TEXT,
        source_url TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
    CREATE VIRTUAL TABLE IF NOT EXISTS vec_entities USING vec0(
        entity_id INTEGER PRIMARY KEY,
        embedding FLOAT[{DIM}]
    );

    CREATE TABLE IF NOT EXISTS relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT,
        target_name TEXT,
        description TEXT,
        strength INTEGER,
        document_url TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_name);
    CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target_name);

    CREATE TABLE IF NOT EXISTS chunk_entities (
        chunk_id INTEGER,
        entity_id INTEGER,
        PRIMARY KEY (chunk_id, entity_id)
    );
    CREATE INDEX IF NOT EXISTS idx_ce_chunk ON chunk_entities(chunk_id);
    CREATE INDEX IF NOT EXISTS idx_ce_entity ON chunk_entities(entity_id);
    """)
    conn.commit()


def serialize(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def upsert_page(conn: sqlite3.Connection, *, url: str, title: str, slug: str,
                summary: str, markdown: str, ingested_at: str) -> None:
    conn.execute(
        "INSERT INTO pages(url, title, slug, summary, markdown, ingested_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(url) DO UPDATE SET title=excluded.title, slug=excluded.slug, "
        "summary=excluded.summary, markdown=excluded.markdown, ingested_at=excluded.ingested_at",
        (url, title, slug, summary, markdown, ingested_at),
    )


def replace_chunks(conn: sqlite3.Connection, page_url: str, chunks: list[dict],
                   embeddings: list[list[float]]) -> list[int]:
    # vec_chunks has no FK, clean it manually before deleting chunks rows.
    old = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE page_url=?", (page_url,)).fetchall()]
    if old:
        conn.execute(
            f"DELETE FROM vec_chunks WHERE chunk_id IN ({','.join('?' * len(old))})",
            old,
        )
        conn.execute(
            f"DELETE FROM chunk_entities WHERE chunk_id IN ({','.join('?' * len(old))})",
            old,
        )
    conn.execute("DELETE FROM chunks WHERE page_url=?", (page_url,))

    new_ids: list[int] = []
    for ch, emb in zip(chunks, embeddings):
        cur = conn.execute(
            "INSERT INTO chunks(page_url, heading_path, text, token_count) VALUES (?, ?, ?, ?)",
            (page_url, ch["heading_path"], ch["text"], ch["token_count"]),
        )
        cid = cur.lastrowid
        new_ids.append(cid)
        conn.execute(
            "INSERT INTO vec_chunks(chunk_id, embedding) VALUES (?, ?)",
            (cid, serialize(emb)),
        )
    return new_ids


def upsert_entity(conn: sqlite3.Connection, *, name: str, type_: str,
                  description: str, source_url: str,
                  embedding: list[float] | None) -> int:
    """Insert-or-merge an entity. On conflict keeps the longer description."""
    row = conn.execute("SELECT id, description FROM entities WHERE name=?", (name,)).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO entities(name, type, description, source_url) VALUES (?, ?, ?, ?)",
            (name, type_, description, source_url),
        )
        eid = cur.lastrowid
        if embedding is not None:
            conn.execute(
                "INSERT INTO vec_entities(entity_id, embedding) VALUES (?, ?)",
                (eid, serialize(embedding)),
            )
        return eid
    eid, existing = row
    if description and len(description) > len(existing or ""):
        conn.execute("UPDATE entities SET description=?, type=? WHERE id=?",
                     (description, type_, eid))
    return eid


def insert_relationship(conn: sqlite3.Connection, *, source: str, target: str,
                        description: str, strength: int, document_url: str) -> None:
    conn.execute(
        "INSERT INTO relationships(source_name, target_name, description, strength, document_url) "
        "VALUES (?, ?, ?, ?, ?)",
        (source, target, description, strength, document_url),
    )


def link_chunk_entities(conn: sqlite3.Connection, chunk_id: int, entity_ids: list[int]) -> None:
    for eid in set(entity_ids):
        conn.execute(
            "INSERT OR IGNORE INTO chunk_entities(chunk_id, entity_id) VALUES (?, ?)",
            (chunk_id, eid),
        )


# ── Search ─────────────────────────────────────────────────────────────────
def vector_search_chunks(conn: sqlite3.Connection, vec: list[float], k: int = 12) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.id, c.page_url, c.heading_path, c.text, p.title, p.summary, v.distance
        FROM vec_chunks v
        JOIN chunks c ON c.id = v.chunk_id
        JOIN pages p ON p.url = c.page_url
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (serialize(vec), k),
    ).fetchall()
    return [
        {"chunk_id": r[0], "url": r[1], "heading_path": r[2], "text": r[3],
         "title": r[4], "summary": r[5], "distance": float(r[6])}
        for r in rows
    ]


def vector_search_entities(conn: sqlite3.Connection, vec: list[float], k: int = 8) -> list[dict]:
    rows = conn.execute(
        """
        SELECT e.id, e.name, e.type, e.description, v.distance
        FROM vec_entities v
        JOIN entities e ON e.id = v.entity_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (serialize(vec), k),
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "type": r[2], "description": r[3], "distance": float(r[4])}
        for r in rows
    ]


def entities_for_chunks(conn: sqlite3.Connection, chunk_ids: list[int]) -> list[dict]:
    if not chunk_ids:
        return []
    qs = ",".join("?" * len(chunk_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT e.id, e.name, e.type, e.description
        FROM entities e
        JOIN chunk_entities ce ON ce.entity_id = e.id
        WHERE ce.chunk_id IN ({qs})
        """,
        chunk_ids,
    ).fetchall()
    return [{"id": r[0], "name": r[1], "type": r[2], "description": r[3]} for r in rows]


def neighbour_relationships(conn: sqlite3.Connection, names: list[str],
                            limit: int = 30) -> list[dict]:
    if not names:
        return []
    qs = ",".join("?" * len(names))
    rows = conn.execute(
        f"""
        SELECT source_name, target_name, description, strength, document_url
        FROM relationships
        WHERE source_name IN ({qs}) OR target_name IN ({qs})
        ORDER BY strength DESC
        LIMIT ?
        """,
        names + names + [limit],
    ).fetchall()
    return [
        {"source": r[0], "target": r[1], "description": r[2],
         "strength": r[3], "document": r[4]}
        for r in rows
    ]


def stats(conn: sqlite3.Connection) -> dict:
    return {
        "pages": conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
        "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "entities": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "relationships": conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0],
    }


# ── JSON graph export (for /api/graph) ─────────────────────────────────────
def export_graph(conn: sqlite3.Connection, path: Path) -> None:
    entities = [
        {"id": r[0], "name": r[1], "type": r[2], "description": r[3], "source_url": r[4]}
        for r in conn.execute(
            "SELECT id, name, type, description, source_url FROM entities"
        ).fetchall()
    ]
    relationships = [
        {"source": r[0], "target": r[1], "description": r[2],
         "strength": r[3], "document": r[4]}
        for r in conn.execute(
            "SELECT source_name, target_name, description, strength, document_url FROM relationships"
        ).fetchall()
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"entities": entities, "relationships": relationships},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
