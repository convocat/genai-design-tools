"""Per-page summary via Anthropic Haiku, prompt pulled from Langfuse."""
from __future__ import annotations

from anthropic import Anthropic

from langfuse_integration import get_prompt

MODEL = "claude-haiku-4-5-20251001"
PROMPT_ID = "mindstudio/summarize-page"


def summarize_page(client: Anthropic, title: str, markdown: str, fallback_text: str,
                   trace=None) -> str:
    system_prompt, prompt_obj = get_prompt(PROMPT_ID, fallback_text)
    user = f"# {title}\n\n{markdown[:8000]}"
    messages = [{"role": "user", "content": user}]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system_prompt,
        messages=messages,
    )
    out = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if trace is not None:
        try:
            from langfuse_integration import extract_usage
            trace.record_generation(
                model=MODEL,
                messages=messages,
                system_prompt=system_prompt,
                output_text=out,
                usage=extract_usage(resp),
                prompt_obj=prompt_obj,
            )
        except Exception:
            pass
    return out
