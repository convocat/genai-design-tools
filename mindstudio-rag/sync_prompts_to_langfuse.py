"""Sync the four MindStudio prompts to Langfuse.

After the first sync, edit prompts in the Langfuse UI; the local .md files
remain only as a fallback when Langfuse is unreachable.

    python sync_prompts_to_langfuse.py --dry-run
    python sync_prompts_to_langfuse.py
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = ROOT / "prompts"

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

PROMPTS = [
    {"file": "answer-system-prompt.md", "name": "mindstudio/answer-system-prompt", "role": "system"},
    {"file": "extract-graph.md",        "name": "mindstudio/extract-graph",        "role": "ingest-node"},
    {"file": "query-rewrite.md",        "name": "mindstudio/query-rewrite",        "role": "retrieval-node"},
    {"file": "summarize-page.md",       "name": "mindstudio/summarize-page",       "role": "ingest-node"},
    {"file": "summarize-community.md",  "name": "mindstudio/summarize-community",  "role": "ingest-node"},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plan: list[dict] = []
    for p in PROMPTS:
        path = PROMPTS_DIR / p["file"]
        if not path.exists():
            print(f"  [skip] missing {path}", file=sys.stderr)
            continue
        body = path.read_text(encoding="utf-8").strip()
        plan.append({
            "name": p["name"],
            "body": body,
            "labels": ["production"],
            "config": {"role": p["role"], "source": str(path.relative_to(ROOT)).replace("\\", "/")},
            "source": str(path),
        })

    if not plan:
        print("No prompts found.")
        return 1

    print(f"Found {len(plan)} prompt(s):")
    for p in plan:
        print(f"  - {p['name']}  (source={p['source']})")

    if args.dry_run:
        print("\nDry run. No changes pushed.")
        return 0

    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        print("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set.", file=sys.stderr)
        return 2

    try:
        from langfuse import Langfuse
    except Exception as e:
        print(f"langfuse SDK not installed: {e}", file=sys.stderr)
        return 2

    client = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )

    pushed = 0
    for p in plan:
        try:
            client.create_prompt(
                name=p["name"], type="text", prompt=p["body"],
                labels=p["labels"], config=p["config"],
            )
            print(f"  [ok]  {p['name']}")
            pushed += 1
        except Exception as e:
            print(f"  [fail] {p['name']}: {e}", file=sys.stderr)

    client.flush()
    print(f"\nSynced {pushed}/{len(plan)} prompt(s).")
    return 0 if pushed == len(plan) else 1


if __name__ == "__main__":
    sys.exit(main())
