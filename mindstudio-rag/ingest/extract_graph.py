"""GraphRAG-style entity + relationship extraction.

Output schema (Microsoft GraphRAG convention):
    entities:      [{name, type, description}]
    relationships: [{source, target, description, strength}]
"""
from __future__ import annotations

import json
import re

from anthropic import Anthropic

from langfuse_integration import extract_usage, get_prompt

MODEL = "claude-haiku-4-5-20251001"
PROMPT_ID = "mindstudio/extract-graph"


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def extract_graph(client: Anthropic, url: str, title: str, markdown: str,
                  fallback_text: str, trace=None) -> dict:
    system_prompt, prompt_obj = get_prompt(PROMPT_ID, fallback_text)
    user = f"URL: {url}\nTitle: {title}\n\n{markdown[:9000]}"
    messages = [{"role": "user", "content": user}]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system_prompt,
        messages=messages,
    )
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    if trace is not None:
        try:
            trace.record_generation(
                model=MODEL, messages=messages, system_prompt=system_prompt,
                output_text=raw, usage=extract_usage(resp), prompt_obj=prompt_obj,
            )
        except Exception:
            pass

    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except Exception:
        return {"entities": [], "relationships": []}

    entities: dict[str, dict] = {}
    for e in data.get("entities") or []:
        name = _normalize_name(e.get("name") or "")
        if not name:
            continue
        entities[name] = {
            "name": name,
            "type": str(e.get("type") or "concept").strip().lower(),
            "description": str(e.get("description") or "").strip(),
            "source": url,
        }

    relationships: list[dict] = []
    for r in data.get("relationships") or []:
        s = _normalize_name(r.get("source") or "")
        t = _normalize_name(r.get("target") or "")
        if not s or not t or s == t:
            continue
        if s not in entities or t not in entities:
            continue
        try:
            strength = int(r.get("strength") or 5)
        except Exception:
            strength = 5
        relationships.append({
            "source": s,
            "target": t,
            "description": str(r.get("description") or "").strip(),
            "strength": max(1, min(10, strength)),
            "document": url,
        })

    return {"entities": list(entities.values()), "relationships": relationships}
