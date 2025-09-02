# ─────────────────────────────────────────────────────────────────────────────
# File: services/retriever_utils.py
# Purpose: Safe, signature-flexible wrappers for semantic retrievers
#          (sync or async), plus lightweight normalization helpers.
#
# Public API:
#   - async safe_semantic_search(retriever, *, query: str, k: int = 6, **kwargs) -> List[dict]
#   - normalize_hit(obj) -> dict
#   - normalize_hits(hits) -> List[dict]
#
# Notes:
#   - Tries common method names in order: search/query/retrieve/get_relevant_documents/callable.
#   - Prefers keyword style (query=..., k=...) then falls back to positional.
#   - Returns a list (possibly empty). Never raises on signature mismatches.
#   - Normalization unifies to {text, score, meta} keys when possible.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------- Normalization ---------------------------------


def normalize_hit(hit: Any) -> Dict[str, Any]:
    """
    Best-effort normalization into:
      {
        "text": str,
        "score": float|None,
        "meta": dict
      }
    Works with:
      - dict-like: text/page_content/content, score/similarity/distance, metadata/meta
      - LangChain Document / custom objects with attributes
    """
    if isinstance(hit, dict):
        text = hit.get("text") or hit.get("page_content") or hit.get("content") or ""
        score = hit.get("score") or hit.get("similarity") or hit.get("distance")
        meta = hit.get("metadata") or hit.get("meta") or {}
        try:
            score = float(score) if score is not None else None
        except Exception:
            score = None
        return {"text": str(text or ""), "score": score, "meta": meta if isinstance(meta, dict) else {}}

    # object with attributes
    text = getattr(hit, "text", None) or getattr(hit, "page_content", None) or ""
    meta = getattr(hit, "metadata", None) or {}
    score = getattr(hit, "score", None) or getattr(hit, "similarity", None) or getattr(hit, "distance", None)
    try:
        score = float(score) if score is not None else None
    except Exception:
        score = None
    return {"text": str(text or ""), "score": score, "meta": meta if isinstance(meta, dict) else {}}


def normalize_hits(hits: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    if not hits:
        return []
    out: List[Dict[str, Any]] = []
    for h in hits:
        try:
            norm = normalize_hit(h)
            # drop empty text rows to reduce junk
            if norm.get("text", "").strip():
                out.append(norm)
        except Exception as e:
            logger.debug("normalize_hit skipped item (%s): %s", type(h), e)
    return out


# ------------------------------ Invokers ------------------------------------


async def _maybe_await(x: Any) -> Any:
    return await x if inspect.isawaitable(x) else x


async def _try_call(fn: Any, *args, **kwargs) -> Optional[Any]:
    """
    Attempt to call a function/method that could be sync or async.
    Returns the result or None if calling fails.
    """
    try:
        res = fn(*args, **kwargs)
        return await _maybe_await(res)
    except TypeError:
        # signature mismatch; let caller try another pattern
        return None
    except Exception as e:
        logger.debug("retriever call failed for %s: %s", getattr(fn, "__name__", fn), e)
        return None


async def safe_semantic_search(retriever: Any, *, query: str, k: int = 6, **kwargs) -> List[Dict[str, Any]]:
    """
    Safely call a variety of retriever styles, returning a normalized list.
    Tries in this order:
      1) obj.search(query=..., k=..., **kwargs)
      2) obj.search(query, k, **kwargs)
      3) obj.query(query, **kwargs)
      4) obj.retrieve(query, **kwargs)
      5) obj.get_relevant_documents(query, **kwargs)
      6) callable(retriever)(query, **kwargs)
    If multiple methods exist, the first successful one wins.
    Never raises on signature mismatches; returns [] on failure.
    """
    if retriever is None:
        return []

    # Prefer keyworded search
    for method_name, positional in (
        ("search", False),
        ("search", True),
        ("query", True),
        ("retrieve", True),
        ("get_relevant_documents", True),
    ):
        fn = getattr(retriever, method_name, None)
        if not callable(fn):
            continue

        # Try keyword style first when possible
        if not positional:
            res = await _try_call(fn, query=query, k=k, **kwargs)
            if res is not None:
                return normalize_hits(res)

        # Fallback positional
        # Many libs accept (query) or (query, k)
        res = await _try_call(fn, query, k, **kwargs)  # may TypeError; _try_call will return None
        if res is not None:
            return normalize_hits(res)

        res = await _try_call(fn, query, **kwargs)
        if res is not None:
            return normalize_hits(res)

    # Callable retriever (function or __call__)
    if callable(retriever):
        res = await _try_call(retriever, query=query, k=k, **kwargs)
        if res is not None:
            return normalize_hits(res)
        res = await _try_call(retriever, query, k, **kwargs)
        if res is not None:
            return normalize_hits(res)
        res = await _try_call(retriever, query, **kwargs)
        if res is not None:
            return normalize_hits(res)

    # Nothing worked
    return []
