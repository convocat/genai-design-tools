"""OpenAI embeddings (text-embedding-3-small)."""
from __future__ import annotations

import os

from openai import OpenAI

MODEL = "text-embedding-3-small"
DIM = 1536  # native dimension for text-embedding-3-small
BATCH = 96


def _client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """input_type kept for API symmetry; OpenAI does not differentiate."""
    if not texts:
        return []
    client = _client()
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        batch = texts[i : i + BATCH]
        resp = client.embeddings.create(model=MODEL, input=batch)
        out.extend(d.embedding for d in resp.data)
    return out


def embed_query(text: str) -> list[float]:
    return embed_texts([text], input_type="query")[0]
