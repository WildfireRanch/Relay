# ──────────────────────────────────────────────────────────────────────────────
# File: services/semantic_retriever.py
# Purpose: Thin wrapper around KB search that supports both `k` and `top_k`,
#          applies an optional score_threshold, and renders readable snippets.
#          Includes legacy shims + an engine-friendly `SemanticRetriever`
#          class for the unified context engine.
#
# Exports:
#   - search(q, top_k|k, score_threshold?) -> List[Dict]
#   - render_markdown(results) -> str
#   - get_semantic_context(query, top_k, score_threshold?) -> str
#   - get_retriever() -> Callable[[str], List[Dict]]
#   - SemanticRetriever(score_threshold: Optional[float]) -> adapter with .search()
#
# Notes:
#   - Does NOT depend on routes/* to avoid circular imports.
#   - KB adapter must be provided by services.kb.search(query: str, k: int, ...)
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Callable, Tuple
import time
from pathlib import Path
import math

# Safe logging shim (avoid hard dependency during early boot)
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    import logging, json
    _LOG = logging.getLogger("relay.semantic")
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        payload = {"event": event, **(data or {})}
        try:
            _LOG.info(json.dumps(payload, default=str))
        except Exception:
            _LOG.info("event=%s data=%s", event, (data or {}))

# Guarded import: degrade gracefully if KB adapter is unavailable
try:  # noqa: SIM105
    from services.kb import search as kb_search  # type: ignore
except Exception as e:  # pragma: no cover
    kb_search = None  # type: ignore[assignment]
    try:
        log_event("semantic_kb_import_failed", {"error": str(e)})
    except Exception:
        pass

def _safe_int(val: Any, default: int) -> int:
    """Parse int safely; return default on any error."""
    try:
        return int(str(val))
    except Exception:
        return default

DEFAULT_K = _safe_int(os.getenv("SEMANTIC_DEFAULT_K"), 6)

def _clean_str(s: Any, max_len: int = 1200) -> str:
    t = ("" if s is None else str(s)).strip()
    return t[:max_len]

def _mk_row(hit: Dict[str, Any]) -> Dict[str, Any]:
    """Map KB hit schema → stable row with normalized score in [0,1]."""
    # KB emits: title, path, tier, snippet, similarity (float), meta
    similarity = hit.get("similarity")
    # Normalize score to [0,1] across potential backends (cosine, IP, etc.)
    def _norm(x: Any) -> Optional[float]:
        try:
            v = float(x)
        except Exception:
            return None
        if not math.isfinite(v):  # NaN/Inf guard
            return None
        if -1.0 <= v <= 1.0:
            # Cosine-like → shift/scale to [0,1]
            v = 0.5 + 0.5 * v
        else:
            # Large positives (e.g., inner product) → logistic-style squash
            v = max(-20.0, min(20.0, v))
            v = 1.0 - (1.0 / (1.0 + math.exp(-v)))
        return max(0.0, min(1.0, v))

    score = _norm(similarity)

    meta = hit.get("meta") or {}
    try:
        if similarity is not None and "_raw_similarity" not in meta:
            # Aid troubleshooting without affecting ranking logic
            meta = {**meta, "_raw_similarity": similarity}
    except Exception:
        pass

    return {
        "title": _clean_str(hit.get("title") or hit.get("node_id") or hit.get("id")),
        "path": _clean_str(hit.get("path") or hit.get("uri") or hit.get("source")),
        "tier": hit.get("tier"),
        "score": score,
        "snippet": _clean_str(hit.get("snippet") or hit.get("text") or hit.get("preview"), 1500),
        "meta": meta,
    }

def search(
    q: str,
    *,
    top_k: Optional[int] = None,
    k: Optional[int] = None,
    score_threshold: Optional[float] = None,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Run semantic search via KB adapter with robust fallbacks.

    - Accepts either `top_k` or `k`; coerces to an integer with defaults.
    - Tolerates backend signature drift by trying multiple param forms.
    - Normalizes results into rows with `score` ∈ [0,1].
    - Applies optional local `score_threshold` after normalization.
    - Never raises on adapter errors; logs and returns [] instead.
    """
    try:
        use_k = int(top_k or k or DEFAULT_K)
    except Exception:
        use_k = DEFAULT_K

    # IMPORTANT: kb.search may accept top_k or k; try both (with/without threshold), then kwargs-free.
    results: List[Dict[str, Any]] = []
    if kb_search is None:
        log_event("semantic_search_degraded", {"reason": "kb_search_unavailable"})
        return []
    try_order = [
        dict(query=q, top_k=use_k, score_threshold=score_threshold, **kwargs),
        dict(query=q, k=use_k,     score_threshold=score_threshold, **kwargs),
        dict(query=q, top_k=use_k),
        dict(query=q, k=use_k),
    ]
    last_err: Optional[Exception] = None
    for params in try_order:
        try:
            out = kb_search(**params) or []
            results = out if isinstance(out, list) else []
            if results:
                break
        except TypeError as e:
            # Signature mismatch; try next form
            last_err = e
            continue
        except Exception as e:
            last_err = e
            # Break on non-TypeError to avoid masking real backend errors
            break
    if last_err and not results:
        log_event("semantic_search_error", {"q_head": q[:180], "error": str(last_err)})
        return [] 

    rows = [_mk_row(h) for h in results if isinstance(h, dict)]
    # Optional local threshold filter (router may also apply its own env threshold)
    if score_threshold is not None:
        try:
            thr = float(score_threshold)
            rows = [r for r in rows if (r.get("score") is not None and float(r["score"]) >= thr)]
        except Exception:
            pass
    log_event("semantic_search_done", {"k": use_k, "rows": len(rows), "thresh": score_threshold})
    return rows

# Public API (explicit for contributors)
__all__ = [
    "search",
    "render_markdown",
    "get_semantic_context",
    "get_retriever",
    "SemanticRetriever",
    "TieredSemanticRetriever",
    "reindex_all",  # public: used by KB reindex path
]

def reindex_all(root: str | Path) -> Dict[str, Any]:
    """
    Contract:
      { ok: bool, status: "done"|"error",
        counts: { documents:int, chunks:int }, took_ms:int, error?:str }
    Pass-1 implementation: fast file walk + conservative chunk estimate.
    """
    t0 = time.perf_counter()
    try:
        root_path = Path(root).expanduser().resolve()
        if not root_path.exists() or not root_path.is_dir():
            took_ms = int((time.perf_counter() - t0) * 1000)
            msg = f"KB root not found or not a directory: {root_path}"
            log_event("semantic_reindex_invalid_root", {"root": str(root_path)})
            return {"ok": False, "status": "error", "counts": {"documents": 0, "chunks": 0}, "took_ms": took_ms, "error": msg}

        allowed = {".md", ".markdown", ".txt"}
        max_chars = 1200
        docs = 0
        chunks = 0
        for fp in root_path.rglob("*"):
            if not (fp.is_file() and fp.suffix.lower() in allowed):
                continue
            docs += 1
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                log_event("semantic_reindex_read_skip", {"path": str(fp), "error": str(e)})
                continue
            parts = [s.strip() for s in text.split("\n\n") if s.strip()]
            if not parts:
                continue
            acc = 0
            for part in parts:
                sz = len(part)
                if acc == 0 or acc + sz <= max_chars:
                    acc = (acc + sz) if acc else sz
                else:
                    chunks += 1
                    acc = sz
            if acc > 0:
                chunks += 1

        took_ms = int((time.perf_counter() - t0) * 1000)
        log_event("semantic_reindex_done", {"docs": docs, "chunks": chunks, "took_ms": took_ms})
        return {"ok": True, "status": "done", "counts": {"documents": docs, "chunks": chunks}, "took_ms": took_ms}
    except Exception as e:
        took_ms = int((time.perf_counter() - t0) * 1000)
        log_event("semantic_reindex_error", {"error": str(e)})
        return {"ok": False, "status": "error", "counts": {"documents": 0, "chunks": 0}, "took_ms": took_ms, "error": str(e)}

def render_markdown(results: List[Dict[str, Any]]) -> str:
    """
    Render compact markdown bullets suitable for prompt injection.
    Example:
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
        meta_bits = []
        if tier is not None:
            meta_bits.append(f"tier: {tier}")
        if score is not None:
            try:
                meta_bits.append(f"score: {float(score):.3f}")
            except Exception:
                meta_bits.append(f"score: {score}")
        meta_str = f" ({', '.join(meta_bits)})" if meta_bits else ""
        lines.append(f"• **{title}** — _{path}_{meta_str}: {tail}")
    return "\n".join(lines)

# ---- Legacy shims (retain backward compatibility) --------------------------

def get_semantic_context(
    query: str,
    *,
    top_k: int = DEFAULT_K,
    score_threshold: Optional[float] = None,
    **kwargs: Any,
) -> str:
    """
    Legacy helper used by context_injector: returns markdown bullets for the query.
    Internally calls `search()` then `render_markdown()`.
    """
    rows = search(query, top_k=top_k, score_threshold=score_threshold, **kwargs)
    md = render_markdown(rows)
    return md or "[No semantic results]"

def get_retriever() -> Callable[[str], List[Dict[str, Any]]]:
    """
    Legacy warmup hook used by main startup: returns a callable retriever.
    """
    def _retriever(q: str, **kw) -> List[Dict[str, Any]]:
        return search(q, **kw)
    log_event("semantic_retriever_ready", {"default_k": DEFAULT_K})
    return _retriever

# ---- Engine-friendly adapter ------------------------------------------------

class SemanticRetriever:
    """
    Adapter for core.context_engine. It does NOT import the engine types to avoid
    accidental circular imports; it simply exposes .search(query, k) returning:
       List[Tuple[path, score, snippet]]
    """
    def __init__(self, score_threshold: Optional[float] = None) -> None:
        self.score_threshold = score_threshold

    def search(self, query: str, k: int) -> List[Tuple[str, float, str]]:
        rows = search(
            q=query,
            k=k,
            score_threshold=self.score_threshold,
        )
        out: List[Tuple[str, float, str]] = []
        for r in rows:
            path = r.get("path") or ""
            score = r.get("score")
            snippet = r.get("snippet") or ""
            if not path or score is None:
                continue
            try:
                out.append((str(path), float(score), str(snippet)))
            except Exception:
                continue
        return out
# Put near SemanticRetriever
class TieredSemanticRetriever(SemanticRetriever):
    """Same as SemanticRetriever, but only returns hits where hit['tier'] == wanted_tier."""
    def __init__(self, wanted_tier: str, score_threshold: Optional[float] = None) -> None:
        super().__init__(score_threshold=score_threshold)
        self.wanted_tier = wanted_tier

    def search(self, query: str, k: int) -> List[Tuple[str, float, str]]:
        rows = search(q=query, k=k, score_threshold=self.score_threshold)
        out = []
        for r in rows:
            if (r.get("tier") or "").strip().lower() != self.wanted_tier:
                continue
            path = r.get("path") or ""
            score = r.get("score")
            snippet = r.get("snippet") or ""
            if path and (score is not None):
                out.append((str(path), float(score), str(snippet)))
        return out
