"""Langfuse integration for the garden chatbot.

Wraps the Langfuse Python SDK so serve.py stays clean and the bot keeps
working when Langfuse is not configured (env vars missing or unreachable).

Two responsibilities:

1. **Tracing**: open a trace per HTTP request, attach a retrieval span (ask)
   and a generation observation, link the generation to a Langfuse prompt
   object so analytics can pivot by prompt version.

2. **Prompt management**: pull system prompts from Langfuse with a short TTL
   cache. On any failure, fall back to the markdown file shipped in the repo,
   so the bot is never blocked on Langfuse availability.

If LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set, every public
function in this module no-ops cheaply. Callers do not need to guard.

Targets Langfuse SDK v4: uses start_as_current_observation(as_type=...) and
propagate_attributes(user_id, session_id, tags, ...) for trace-level fields.
"""
from __future__ import annotations

import os
import sys
import threading
from typing import Any, Optional


_IMPORT_ERROR: Optional[Exception] = None
try:
    from langfuse import Langfuse, propagate_attributes  # type: ignore
except Exception as e:  # pragma: no cover
    Langfuse = None  # type: ignore
    propagate_attributes = None  # type: ignore
    _IMPORT_ERROR = e


_client_lock = threading.Lock()
_client: Optional[Any] = None
_client_initialized = False


def _env_configured() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def get_client() -> Optional[Any]:
    """Return a Langfuse client, or None if not configured / SDK unavailable."""
    global _client, _client_initialized
    if _client_initialized:
        return _client
    with _client_lock:
        if _client_initialized:
            return _client
        _client_initialized = True
        if Langfuse is None:
            print(f"[langfuse] SDK not installed: {_IMPORT_ERROR}", file=sys.stderr)
            return None
        if not _env_configured():
            return None
        try:
            _client = Langfuse(
                public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
        except Exception as e:
            print(f"[langfuse] init failed: {e}", file=sys.stderr)
            _client = None
        return _client


# ── Prompt management ───────────────────────────────────────────────────────

def get_prompt(prompt_id: str, fallback_text: str, label: str = "production") -> tuple[str, Optional[Any]]:
    """Return (compiled_prompt_text, langfuse_prompt_object_or_None).

    Tries Langfuse first (with the SDK's built-in 60s TTL cache). On any
    failure, returns the fallback text and None. Pass the returned prompt
    object to record_generation() so the trace is linked to the version.
    """
    client = get_client()
    if client is None:
        return fallback_text, None
    try:
        prompt = client.get_prompt(prompt_id, label=label, cache_ttl_seconds=60)
        text = getattr(prompt, "prompt", None)
        if isinstance(text, str) and text.strip():
            return text, prompt
        return fallback_text, None
    except Exception as e:
        print(f"[langfuse] get_prompt({prompt_id!r}) failed, using fallback: {e}", file=sys.stderr)
        return fallback_text, None


# ── Tracing ─────────────────────────────────────────────────────────────────

class _NoOpTrace:
    """Returned when Langfuse is not available. Every method is a no-op."""
    def record_retrieval(self, *_a, **_kw): pass
    def record_generation(self, *_a, **_kw): pass
    def set_output(self, *_a, **_kw): pass
    def set_error(self, *_a, **_kw): pass
    def add_tag(self, *_a, **_kw): pass


class _Trace:
    """Thin wrapper over a Langfuse v4 root observation.

    A trace = one HTTP request = one user turn. We open a root span and a
    propagate_attributes context so user_id / session_id / tags apply to
    all child observations created on this trace.
    """
    def __init__(self, client: Any, name: str, user_id: str, session_id: str,
                 input_text: str, metadata: dict, tags: list[str]):
        self._client = client
        self._closed = False
        self._span_cm = client.start_as_current_observation(
            name=name,
            as_type="span",
            input=input_text,
            metadata=metadata,
        )
        self._span = self._span_cm.__enter__()
        # Capture the OTEL context that now holds our root span as active.
        # We re-attach this context inside record_*() calls so child
        # observations nest correctly even when fired from a different
        # thread / async task (e.g. a streaming response generator).
        self._otel_ctx = None
        try:
            from opentelemetry import context as _otel_context  # type: ignore
            self._otel_context = _otel_context
            self._otel_ctx = _otel_context.get_current()
        except Exception:
            self._otel_context = None
        self._props_cm = None
        try:
            kwargs: dict[str, Any] = {"trace_name": name}
            if user_id:
                kwargs["user_id"] = user_id
            if session_id:
                kwargs["session_id"] = session_id
            if tags:
                kwargs["tags"] = tags
            self._props_cm = propagate_attributes(**kwargs)
            self._props_cm.__enter__()
        except Exception as e:
            print(f"[langfuse] propagate_attributes failed: {e}", file=sys.stderr)
            self._props_cm = None

    def _with_context(self):
        """Re-attach the captured OTEL context. Returns a token to detach with."""
        if self._otel_context is None or self._otel_ctx is None:
            return None
        try:
            return self._otel_context.attach(self._otel_ctx)
        except Exception:
            return None

    def _detach(self, token) -> None:
        if token is None or self._otel_context is None:
            return
        try:
            self._otel_context.detach(token)
        except Exception:
            pass

    def record_retrieval(self, question: str, retrieval_debug: dict) -> None:
        token = self._with_context()
        try:
            with self._client.start_as_current_observation(
                name="retrieval",
                as_type="span",
                input=question,
                metadata=retrieval_debug,
            ) as span:
                span.update(output={
                    "matched_articles": retrieval_debug.get("matched_articles", []),
                    "matched_topics": retrieval_debug.get("matched_topics", []),
                    "fired_triples": retrieval_debug.get("fired_triples", []),
                    "matched_themes": retrieval_debug.get("matched_themes", []),
                    "fallback": retrieval_debug.get("fallback", False),
                })
        except Exception as e:
            print(f"[langfuse] record_retrieval failed: {e}", file=sys.stderr)
        finally:
            self._detach(token)

    def record_generation(self, *, model: str, messages: list, system_prompt: str,
                          output_text: str, usage: Optional[dict] = None,
                          prompt_obj: Optional[Any] = None) -> None:
        token = self._with_context()
        try:
            obs_kwargs: dict[str, Any] = {
                "name": "generation",
                "as_type": "generation",
                "model": model,
                "input": {"system": system_prompt, "messages": messages},
            }
            if prompt_obj is not None:
                obs_kwargs["prompt"] = prompt_obj
            with self._client.start_as_current_observation(**obs_kwargs) as gen:
                update_kwargs: dict[str, Any] = {"output": output_text}
                if usage:
                    update_kwargs["usage_details"] = usage
                gen.update(**update_kwargs)
        except Exception as e:
            print(f"[langfuse] record_generation failed: {e}", file=sys.stderr)
        finally:
            self._detach(token)

    def set_output(self, text: str) -> None:
        try:
            self._span.update(output=text)
        except Exception:
            pass

    def set_error(self, error: str) -> None:
        try:
            self._span.update(output={"error": error}, level="ERROR", status_message=error)
        except Exception:
            pass

    def add_tag(self, tag: str) -> None:
        # Tags propagate via propagate_attributes; not adding ad-hoc tags
        # post-hoc to keep the API simple. No-op.
        pass

    def end(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._props_cm is not None:
            try:
                self._props_cm.__exit__(None, None, None)
            except Exception:
                pass
        try:
            self._span_cm.__exit__(None, None, None)
        except Exception:
            pass


def start_trace(*, name: str, user_id: str = "", session_id: str = "",
                input_text: str = "", metadata: Optional[dict] = None,
                tags: Optional[list[str]] = None) -> Any:
    """Open a trace. Returns either a real _Trace or a _NoOpTrace."""
    client = get_client()
    if client is None:
        return _NoOpTrace()
    try:
        return _Trace(
            client=client,
            name=name,
            user_id=user_id or "",
            session_id=session_id or "",
            input_text=input_text or "",
            metadata=metadata or {},
            tags=tags or [],
        )
    except Exception as e:
        print(f"[langfuse] start_trace failed: {e}", file=sys.stderr)
        return _NoOpTrace()


def end_trace(trace: Any) -> None:
    if isinstance(trace, _Trace):
        trace.end()


def flush() -> None:
    """Flush queued events. Required on serverless before the function returns."""
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as e:
        print(f"[langfuse] flush failed: {e}", file=sys.stderr)


def extract_usage(final_message: Any) -> Optional[dict]:
    """Pull token usage from an Anthropic stream's final message into the
    Langfuse usage_details shape. Returns None if no usage is available."""
    if final_message is None:
        return None
    usage = getattr(final_message, "usage", None)
    if usage is None:
        return None
    out: dict[str, int] = {}
    for src, dst in (
        ("input_tokens", "input"),
        ("output_tokens", "output"),
        ("cache_creation_input_tokens", "cache_creation_input_tokens"),
        ("cache_read_input_tokens", "cache_read_input_tokens"),
    ):
        v = getattr(usage, src, None)
        if isinstance(v, int):
            out[dst] = v
    return out or None
