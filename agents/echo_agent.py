# ──────────────────────────────────────────────────────────────────────────────
# File: agents/echo_agent.py
# Purpose: Non-parroting answerer. Exposes async answer(...) and a SAFE-MODE
#          sync shim invoke(query, context, …) used by /mcp fallback paths.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(event: str, data: Optional[Dict[str, Any]] = None) -> None:
        pass

DEFAULT_MODEL = "gpt-4o"

def _strip(s: Any) -> str:
    return ("" if s is None else str(s)).strip()

def _anti_parrot_head(q: str) -> str:
    key = (_strip(q) or "answer").split("\n", 1)[0][:60]
    return f"{key}:"

async def answer(
    *,
    query: str,
    context: Any,
    debug: bool = False,
    request_id: Optional[str] = None,
    timeout: int = 20,
    model: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Async core that returns a structured dict compatible with /mcp routes.
    """
    model = model or DEFAULT_MODEL
    q = _strip(query)
    ctx = _strip(context)

    # Simple local synth (placeholder for actual LLM call)
    # Avoid parroting by prefacing with a minimal head only when helpful.
    head = _anti_parrot_head(q)
    final = f"{head} {q if len(q) <= 200 else q[:200] + '…'}"
    if ctx:
        final += f"\n\nContext:\n{ctx}"

    out = {
        "text": final,
        "answer": final,
        "response": {"model": model, "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "raw": None},
        "meta": {"origin": "echo", "model": model, "request_id": request_id},
    }
    log_event("echo_answer", {"request_id": request_id, "chars": len(final)})
    return out

# ---- SAFE MODE shim (sync) ---------------------------------------------------

# agents/echo_agent.py

def invoke(
    *,
    query: str,
    context: Any = "",
    user_id: Optional[str] = None,
    corr_id: Optional[str] = None,
    debug: bool = False,
    timeout: int = 20,
    model: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    PURE SYNC safe-mode path (no asyncio). Mirrors `answer()` logic inline
    so callers that cannot await never interact with the event loop.
    """
    try:
        m = model or DEFAULT_MODEL
        q = _strip(query)
        ctx = _strip(context)
        head = _anti_parrot_head(q)

        final = f"{head} {q if len(q) <= 200 else q[:200] + '…'}"
        if ctx:
            final += f"\n\nContext:\n{ctx}"

        out = {
            "text": final,
            "answer": final,
            "response": {"model": m, "usage": {"prompt_tokens": 0, "completion_tokens": 0}, "raw": None},
            "meta": {"origin": "echo", "model": m, "request_id": corr_id},
        }
        log_event("echo_answer", {"request_id": corr_id, "chars": len(final)})
        return out
    except Exception as e:
        log_event("echo_invoke_error", {"request_id": corr_id, "error": str(e or "")})
        return {"text": "", "response": {"model": model or DEFAULT_MODEL, "raw": None}, "meta": {"origin": "echo"}}
