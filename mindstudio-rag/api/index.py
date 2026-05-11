"""Vercel serverless entry point.

Vercel auto-detects an ASGI app exported as `app` in `api/*.py` and routes
the matching path to it. The FastAPI app lives in `serve.py` at the repo
root; this file just re-exports it so Vercel can find it.

The same FastAPI app handles all /api/* routes locally (uvicorn) and in
production (Vercel Python runtime).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Route stdlib `import sqlite3` to pysqlite3-binary before any other
# module imports it. Vercel's stdlib sqlite3 is compiled without
# loadable-extension support, which breaks sqlite-vec.
try:
    import pysqlite3  # type: ignore
    sys.modules["sqlite3"] = pysqlite3
except ImportError:
    pass

# Make the bot's modules importable on Vercel (where the working dir differs).
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Vercel runs from a read-only deployment root; the bundled corpus.db is
# accessible at the same relative path the rest of the code uses.
os.environ.setdefault("MINDSTUDIO_RAG_ROOT", str(_ROOT))

from serve import app  # noqa: E402,F401
