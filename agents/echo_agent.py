# ──────────────────────────────────────────────────────────────────────────────
# File: agents/echo_agent.py
# Purpose: Deterministic, non-parroting answerer used by /mcp and /ask.
#          - async `answer(...)` for rich callers
#          - PURE SYNC `invoke(...)` SAFE-MODE shim (no event loop gymnastics)
# Design goals:
#   • Never echo the user's prompt verbatim (passes anti-parrot in /ask)
#   • If context is available, emit 1–3 concise bullets derived from it
#   • If no context, emit a minimal, safe one-liner (still non-parroting)
#   • Keep return types stable for both call paths
# Connectivity audit:
#   - routes.mcp → agents.echo_agent.invoke(query, context, user_id, corr_id, debug)
#   - /mcp uses the string returned by invoke(); /ask wraps MCP result
#   - No async/await in invoke(); no event-loop bridging
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import time
from typing import Any, Dict, Optional

# Lightweight logging that won’t crash if core.logging is absent
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(event: str, data: Optional[Dict[str, Any]] = None) -> None:
        pass

DEFAULT_MODEL = "gpt-4o"

def _s(val: Any) -> str:
    return "" if val is None else str(val).strip()

def _pick_bullets(ctx: str, prompt: str, limit: int = 3) -> list[str]:
    """
    Heuristic: pick first non-empty lines that aren't headings/quotes
    and do NOT begin with the user's prompt text (prevents parroting).
    """
    bullets: list[str] = []
    if not ctx:
        return bullets
    pfx = (_s(prompt).lower()[:48]) if prompt else ""
    for raw in ctx.splitlines():
        line = raw.strip().lstrip("-•#*> ")
        if not line:
            continue
        if pfx and line.lower().startswith(pfx):
            continue
        bullets.append(line)
        if len(bullets) >= limit:
            break
    return bullets

# ──────────────────────────────────────────────────────────────────────────────
# Async core (kept for richer callers; not used by SAFE-MODE)
# Returns a structured dict, but never echoes the prompt.
# ──────────────────────────────────────────────────────────────────────────────
async def answer(
    *,
    query: str,
    context: Any,
    debug: bool = False,
    request_id: Optional[str] = None,
    corr_id: Optional[str] = None,
    timeout: int = 20,
    model: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    model = model or DEFAULT_MODEL
    t0 = time.perf_counter()
    q = _s(query)
    ctx = _s(context)
    bullets = _pick_bullets(ctx, q, limit=3)

    if bullets:
        final = "• " + "\n• ".join(bullets)
    else:
        final = "Here’s a concise answer based on available context."

    out = {
        "text": final,
        "answer": final,
        "response": {"model": model, "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "raw": None},
        "meta": {"origin": "echo", "model": model, "request_id": request_id},
    }
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    log_event(
        "echo_answer",
        {
            "request_id": request_id,
            "corr_id": corr_id or request_id,
            "chars": len(final),
            "elapsed_ms": elapsed_ms,
        },
    )
    return out

# ──────────────────────────────────────────────────────────────────────────────
# PURE SYNC SAFE-MODE shim for /mcp → never touches asyncio
# Returns a STRING so routes.mcp can embed it directly.
# ──────────────────────────────────────────────────────────────────────────────
def invoke(
    *,
    query: str,
    context: Any = "",
    user_id: Optional[str] = None,
    corr_id: Optional[str] = None,
    debug: bool = False,
    timeout: int = 20,
    model: Optional[str] = None,
    **_: Any,  # tolerate extras
) -> str:
    t0 = time.perf_counter()
    try:
        q = _s(query)
        ctx = _s(context)

        bullets = _pick_bullets(ctx, q, limit=3)
        if bullets:
            final = "• " + "\n• ".join(bullets)
        else:
            final = "Here’s a concise answer based on available context."

        log_event(
            "echo_answer",
            {
                "request_id": corr_id,
                "corr_id": corr_id,
                "chars": len(final),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            },
        )
        return final
    except Exception as e:
        # SAFE-MODE must not raise; return minimal text
        log_event(
            "echo_invoke_error",
            {
                "request_id": corr_id,
                "corr_id": corr_id,
                "error": str(e or ""),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            },
        )
        return ""

# ──────────────────────────────────────────────────────────────────────────────
# Streaming interface for /ask/stream endpoint
# ──────────────────────────────────────────────────────────────────────────────
async def stream(
    *,
    query: str,
    context: str = "",
    user_id: str = "anonymous",
    corr_id: Optional[str] = None,
    **kwargs,
):
    """
    Async generator that yields streaming response chunks.
    Compatible with FastAPI StreamingResponse for /ask/stream endpoint.
    """
    import asyncio

    try:
        # Get the full response first
        result = await answer(
            query=query,
            context=context,
            corr_id=corr_id,
            **kwargs
        )
        final_text = result.get("text", "") or result.get("answer", "")

        if not final_text:
            yield "No response generated."
            return

        # Stream in word chunks for better UX
        words = final_text.split()
        chunk_size = 3  # 3 words per chunk

        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if i + chunk_size < len(words):
                chunk += " "
            yield chunk
            # Small delay for streaming effect
            await asyncio.sleep(0.05)

    except Exception as e:
        log_event(
            "echo_stream_error",
            {
                "corr_id": corr_id,
                "error": str(e),
            },
        )
        yield f"[Stream error: {str(e)}]"
