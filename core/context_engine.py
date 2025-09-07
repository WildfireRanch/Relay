# File: core/context_engine.py
# Directory: core
# Purpose: Deterministic, tiered context assembly with reranker thresholds and
#          structured grounding for MCP + /ask gate.
#
# Output (dict):
#   {
#     "context": str,                  # pretty, human-readable context block (UI/debug)
#     "files_used": List[dict],        # optional file metadata
#     "matches": List[{path, score}],  # structured grounding for MCP (/ask reads this)
#   }
#
# Env (optional):
#   TIER_ORDER                 (default "global,context,project_docs,code")
#   RERANK_MIN_SCORE_GLOBAL    (default "0.20")   # tier-wise thresholds
#   RERANK_MIN_SCORE_CONTEXT   (default "0.25")
#   RERANK_MIN_SCORE_DOCS      (default "0.30")
#   RERANK_MIN_SCORE_CODE      (default "0.28")
#   TOPK_PER_TIER_GLOBAL       (default "4")
#   TOPK_PER_TIER_CONTEXT      (default "6")
#   TOPK_PER_TIER_DOCS         (default "12")
#   TOPK_PER_TIER_CODE         (default "10")

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from services.token_budget import (
    DEFAULT_TIERS,
    TierSpec,
    estimate_tokens,
    pack_tier_chunks,
)

# Optional logging (best-effort)
try:
    from core.logging import log_event
except Exception:  # pragma: no cover
    def log_event(evt: str, payload: Dict[str, Any]) -> None:  # type: ignore
        pass

# Optional KB service
try:
    from services import kb  # type: ignore
except Exception:  # pragma: no cover
    kb = None  # type: ignore


# ── Tunables ────────────────────────────────────────────────────────────────
TIER_ORDER = [s.strip() for s in os.getenv("TIER_ORDER", "global,context,project_docs,code").split(",") if s.strip()]

RERANK_MIN_SCORE_GLOBAL  = float(os.getenv("RERANK_MIN_SCORE_GLOBAL",  "0.20"))
RERANK_MIN_SCORE_CONTEXT = float(os.getenv("RERANK_MIN_SCORE_CONTEXT", "0.25"))
RERANK_MIN_SCORE_DOCS    = float(os.getenv("RERANK_MIN_SCORE_DOCS",    "0.30"))
RERANK_MIN_SCORE_CODE    = float(os.getenv("RERANK_MIN_SCORE_CODE",    "0.28"))

TOPK_PER_TIER_GLOBAL  = int(os.getenv("TOPK_PER_TIER_GLOBAL",  "4"))
TOPK_PER_TIER_CONTEXT = int(os.getenv("TOPK_PER_TIER_CONTEXT", "6"))
TOPK_PER_TIER_DOCS    = int(os.getenv("TOPK_PER_TIER_DOCS",    "12"))
TOPK_PER_TIER_CODE    = int(os.getenv("TOPK_PER_TIER_CODE",    "10"))

MIN_SCORE_BY_TIER = {
    "global":       RERANK_MIN_SCORE_GLOBAL,
    "context":      RERANK_MIN_SCORE_CONTEXT,
    "project_docs": RERANK_MIN_SCORE_DOCS,
    "code":         RERANK_MIN_SCORE_CODE,
}

TOPK_BY_TIER = {
    "global":       TOPK_PER_TIER_GLOBAL,
    "context":      TOPK_PER_TIER_CONTEXT,
    "project_docs": TOPK_PER_TIER_DOCS,
    "code":         TOPK_PER_TIER_CODE,
}


# ── Helpers ─────────────────────────────────────────────────────────────────
def _search_tier(tier: str, query: str, files: List[str]) -> List[Dict[str, Any]]:
    """
    Query the KB by tier. This function expects services.kb.search_tier or kb.search
    to exist; it falls back gracefully if the function is missing.
    Returns a list of {path, score, text, tier}
    """
    results: List[Dict[str, Any]] = []

    # Preferred: tier-aware search (if implemented in your kb service)
    if kb and hasattr(kb, "search_tier"):
        try:
            raw = kb.search_tier(query=query, tier=tier, files=files, k=TOPK_BY_TIER.get(tier, 8))  # type: ignore
            for r in raw or []:
                results.append(
                    {
                        "path": r.get("path") or r.get("id") or "",
                        "score": float(r.get("score") or 0.0),
                        "text": r.get("text") or "",
                        "tier": tier,
                    }
                )
            return results
        except Exception:
            pass

    # Fallback: generic kb.search(query, k) without tier semantics
    if kb and hasattr(kb, "search"):
        try:
            raw = kb.search(query=query, k=TOPK_BY_TIER.get(tier, 8))  # type: ignore
            for r in raw or []:
                results.append(
                    {
                        "path": r.get("path") or r.get("id") or "",
                        "score": float(r.get("score") or 0.0),
                        "text": r.get("text") or "",
                        "tier": tier,
                    }
                )
        except Exception:
            pass

    return results


def _filter_and_take(results: List[Dict[str, Any]], tier: str) -> List[Dict[str, Any]]:
    """Apply tier reranker threshold and top-k."""
    if not results:
        return []
    min_score = MIN_SCORE_BY_TIER.get(tier, 0.0)
    k = TOPK_BY_TIER.get(tier, 8)
    keep = [r for r in results if float(r.get("score") or 0.0) >= min_score]
    keep.sort(key=lambda x: float(x.get("score") or 0.0), reverse=True)
    return keep[:k]


def _make_pretty_block(tier: str, items: List[Dict[str, Any]]) -> str:
    """Human-readable context block for debugging/UX."""
    if not items:
        return ""
    lines = [f"## {tier.upper()} — Top Matches (min_score={MIN_SCORE_BY_TIER.get(tier):.2f})"]
    for it in items:
        path = it.get("path", "")
        score = float(it.get("score") or 0.0)
        snippet = (it.get("text") or "").strip()
        # keep the block readable but compact
        if len(snippet) > 300:
            snippet = snippet[:297].rstrip() + "…"
        lines.append(f"• **{path}** (score: {score:.3f})\n{snippet}")
    return "\n".join(lines)


# ── Public API ──────────────────────────────────────────────────────────────
def build_context(
    query: str,
    files: List[str] | None = None,
    topics: List[str] | None = None,
    debug: bool = False,
    corr_id: str | None = None,
) -> Dict[str, Any]:
    """
    Build deterministic, tiered context and structured matches.
    - Honors per-tier thresholds and top-k.
    - Enforces token caps (by tier) using services.token_budget.
    - Returns 'matches' for MCP to surface as structured grounding.
    """
    files = files or []
    topics = topics or []
    corr_id = corr_id or "no-corr"

    log_event("ctx_build_start", {"corr_id": corr_id, "q": query, "files": len(files), "topics": len(topics)})

    # 1) Gather raw candidates per tier
    tier_buckets: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TIER_ORDER}
    for tier in TIER_ORDER:
        try:
            tier_buckets[tier] = _filter_and_take(_search_tier(tier, query, files), tier)
        except Exception as e:
            log_event("ctx_search_error", {"corr_id": corr_id, "tier": tier, "err": str(e)})
            tier_buckets[tier] = []

    # 2) Build per-tier packed text with deterministic caps
    packed_blocks: List[str] = []
    structured_matches: List[Dict[str, Any]] = []
    files_used: List[Dict[str, Any]] = []

    for tier in TIER_ORDER:
        items = tier_buckets.get(tier, [])
        if not items:
            continue

        # Remember structured grounding
        for it in items:
            structured_matches.append({"path": it.get("path", ""), "score": float(it.get("score") or 0.0)})

        # Pack text snippets under the tier token budget
        # Prefer item["text"]; if empty, use just a line with path/score
        raw_chunks: List[str] = []
        for it in items:
            path = it.get("path", "")
            score = float(it.get("score") or 0.0)
            text = (it.get("text") or "").strip()
            if text:
                raw_chunks.append(f"[{tier}] {path} (score {score:.3f})\n{text}")
            else:
                raw_chunks.append(f"[{tier}] {path} (score {score:.3f})")

        tier_spec: TierSpec = DEFAULT_TIERS.get(tier, DEFAULT_TIERS["context"])
        packed_text, used_chunks = pack_tier_chunks(raw_chunks, tier_spec, allow_summarize=True, extractive_sentences=3)

        if packed_text:
            # Add a small header for readability (optional; harmless to model)
            header = _make_pretty_block(tier, items[: max(1, min(3, len(items)))])
            block = f"{header}\n\n{packed_text}" if header else packed_text
            packed_blocks.append(block)

        # Track files used (basic)
        for it in items:
            if it.get("path"):
                files_used.append({"path": it["path"], "tier": tier, "score": float(it.get("score") or 0.0)})

    # 3) Final pretty context (order-preserving)
    pretty_context = "\n\n".join(packed_blocks)

    log_event(
        "ctx_build_done",
        {
            "corr_id": corr_id,
            "tiers": TIER_ORDER,
            "matches": len(structured_matches),
            "context_tokens": estimate_tokens(pretty_context),
        },
    )

    return {
        "context": pretty_context,
        "files_used": files_used,
        "matches": structured_matches,
    }
