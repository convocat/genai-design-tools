"""Heading-aware chunking: ~600 tokens per chunk, 80-token overlap."""
from __future__ import annotations

import re

import tiktoken

ENC = tiktoken.get_encoding("cl100k_base")
TARGET = 600
OVERLAP = 80


def _tok_count(text: str) -> int:
    return len(ENC.encode(text))


def chunk_markdown(url: str, title: str, markdown: str) -> list[dict]:
    """Split markdown into chunks. Each chunk carries its heading path."""
    if not markdown.strip():
        return []

    # Split by ATX headings, keep the heading attached to the following block.
    blocks: list[tuple[list[str], str]] = []
    current_headings: list[str] = [title]
    buf: list[str] = []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            blocks.append((list(current_headings), text))
        buf.clear()

    for line in markdown.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            flush()
            level = len(m.group(1))
            heading = m.group(2).strip()
            current_headings = current_headings[: level - 1 + 1]  # trim
            while len(current_headings) < level:
                current_headings.append("")
            if len(current_headings) >= level:
                current_headings = current_headings[: level - 1] + [heading]
            else:
                current_headings.append(heading)
        else:
            buf.append(line)
    flush()

    # Pack blocks into ~TARGET token chunks.
    chunks: list[dict] = []
    cur_tokens: list[int] = []
    cur_text: list[str] = []
    cur_path: list[str] = []

    def emit():
        if not cur_text:
            return
        text = "\n\n".join(cur_text).strip()
        if not text:
            return
        chunks.append({
            "url": url,
            "heading_path": " > ".join(p for p in cur_path if p),
            "text": text,
            "token_count": sum(cur_tokens),
        })

    for headings, text in blocks:
        toks = _tok_count(text)
        if cur_tokens and sum(cur_tokens) + toks > TARGET:
            emit()
            # overlap: keep the tail of the previous chunk
            if chunks:
                tail_tokens = ENC.encode(chunks[-1]["text"])[-OVERLAP:]
                tail = ENC.decode(tail_tokens)
                cur_text = [tail]
                cur_tokens = [len(tail_tokens)]
            else:
                cur_text = []
                cur_tokens = []
        if not cur_path:
            cur_path = headings
        cur_text.append(text)
        cur_tokens.append(toks)
    emit()

    return chunks
