# File: semantic_retriever.py
# Directory: services
# Purpose: Thin wrapper around KB search that supports both `k` and `top_k`,
#          applies an optional score_threshold, and renders readable snippets.
#
# Upstream:
#   - ENV (optional): SEMANTIC_DEFAULT_K (default 6)
#   - Imports: typing, os, core.logging.log_event, services.kb.search
#
# Downstream:
#   - agents.echo_agent (for answer synthesis)
#   - services.context_injector (to build CONTEXT sections)
#
# Contents:
#   - search(q, *, top_k=None, k=None, score_threshold=None, **kwargs) -> list[dict]
#   - render_markdown(results: list[dict]) -> str

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core.logging import log_event
from services.kb import search as kb_search

DEFAULT_K = int(os.getenv("SEMANTIC_DEFAULT_K", "6"))


def _clean_str(s: Any, max_len: int = 1200) -> str:
    t = ("" if s is None else str(s)).strip()
    return t[:max_len]


def _mk_row(hit: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": _clean_str(hit.get("title") or hit.get("node_id") or hit.get("id")),
        "path": _clean_str(hit.get("path") or hit.get("uri") or hit.get("source")),
        "tier": hit.get("tier"),
        "score": float(hit.get("score")) if hit.get("score") is not None else None,
        "snippet": _clean_str(hit.get("snippet") or hit.get("text") or hit.get("preview"), 1500),
        "meta": hit.get("meta") or {},
    }


def search(
    q: str,
    *,
    top_k: Optional[int] = None,
    k: Optional[int] = None,
    score_threshold: Optional[float] = None,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """
    Compatibility wrapper for KB search:
      - Accepts either `k` or `top_k` (prefers top_k if provided).
      - Forwards score_threshold where supported (optional).
      - Returns a normalized list of rows with title/path/tier/score/snippet/meta.
    """
    use_k = int(top_k or k or DEFAULT_K)
    try:
        results = kb_search(
            q=q,
            k=use_k,
            score_threshold=score_threshold,
            **kwargs,
        ) or []
    except Exception as e:
        log_event("semantic_search_error", {"q_head": q[:180], "error": str(e)})
        return []

    # Normalize each hit
    rows = [_mk_row(h) for h in results if isinstance(h, dict)]
    log_event("semantic_search_done", {"k": use_k, "rows": len(rows), "thresh": score_threshold})
    return rows


def render_markdown(results: List[Dict[str, Any]]) -> str:
    """
    Render compact markdown bullets suitable for prompt injection.
    Example row:
      • **Title** — _path_ (tier: X, score: 0.87): snippet...
    """
    if not results:
        return ""
    lines = []
    for r in results:
        title = r.get("title") or "Untitled"
        path = r.get("path") or ""
        tier = r.get("tier")
        score = r.get("score")
        tail = r.get("snippet") or ""
        meta = []
        if tier is not None:
            meta.append(f"tier: {tier}")
        if score is not None:
            try:
                meta.append(f"score: {float(score):.3f}")
            except Exception:
                meta.append(f"score: {score}")
        meta_str = f" ({', '.join(meta)})" if meta else ""
        lines.append(f"• **{title}** — _{path}_{meta_str}: {tail}")
    return "\n".join(lines)
