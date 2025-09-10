# ──────────────────────────────────────────────────────────────────────────────
# File: core/context_engine.py
# Purpose: Single authoritative context engine for /ask and /mcp pipelines.
#          Deterministic tiered retrieval with tunable Top-K, score thresholds,
#          normalized scores, and token budgeting.
#
# Upstream:
#   - ENV (optional):
#       TOPK_GLOBAL, TOPK_CONTEXT, TOPK_PROJECT_DOCS, TOPK_CODE
#       RERANK_MIN_SCORE_GLOBAL, RERANK_MIN_SCORE_CONTEXT,
#       RERANK_MIN_SCORE_PROJECT_DOCS, RERANK_MIN_SCORE_CODE
#       MAX_CONTEXT_TOKENS
#   - Adapters (required at call site): retrievers per tier implementing `Retriever`.
#
# Downstream:
#   - Routers/Agents call build_context() and consume ContextResult.
#
# Notes:
#   - No imports from routes/main to avoid circularity.
#   - Will use services.token_budget if present; otherwise uses internal estimator.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import importlib
import os
import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, TypedDict

try:
    # Optional precise tokenization if available in the project
    import tiktoken  # type: ignore
    _HAS_TIKTOKEN = True
except Exception:
    _HAS_TIKTOKEN = False


# ──────────────────────────────────────────────────────────────────────────────
# Public models (importable by routes/agents)
# ──────────────────────────────────────────────────────────────────────────────

class RetrievalTier(str, Enum):
    GLOBAL = "global"
    CONTEXT = "context"
    PROJECT_DOCS = "project_docs"
    CODE = "code"


class Match(TypedDict):
    path: str
    score: float  # normalized [0,1]
    tier: str
    snippet: str


class KBMeta(TypedDict):
    hits: int
    max_score: float
    sources: List[str]


class ContextResult(TypedDict):
    context: str
    files_used: List[str]
    matches: List[Match]
    meta: Dict[str, KBMeta]


@dataclass
class ContextRequest:
    query: str
    corr_id: Optional[str] = None
    max_tokens: Optional[int] = None  # override MAX_CONTEXT_TOKENS if needed


class Retriever:
    """
    Adapter interface that concrete tiers must implement.
    Returns a list of (path, raw_score, snippet) where raw_score is unbounded (e.g., cosine sim).
    The engine will normalize to [0,1].
    """

    def search(self, query: str, k: int) -> List[Tuple[str, float, str]]:
        raise NotImplementedError


@dataclass
class EngineConfig:
    """Provide retrievers per tier. Missing tiers are simply skipped."""
    retrievers: Dict[RetrievalTier, Retriever]


# ──────────────────────────────────────────────────────────────────────────────
# Token budgeting (optional external, internal fallback)
# ──────────────────────────────────────────────────────────────────────────────

def _approx_token_count(text: str) -> int:
    """Cheap estimator: ~4 chars/token (English prose)."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))

def _tiktoken_count(text: str, model: str = "gpt-4o") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)  # type: ignore
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")  # type: ignore
    return len(enc.encode(text))  # type: ignore

def _load_external_token_budget():
    try:
        mod = importlib.import_module("services.token_budget")
        # Expect optional callable: tokens(text: str) -> int
        counter = getattr(mod, "tokens", None)
        if callable(counter):
            return counter
    except Exception:
        pass
    return None

_EXTERNAL_COUNTER = _load_external_token_budget()

def count_tokens(text: str) -> int:
    if _EXTERNAL_COUNTER:
        try:
            return int(_EXTERNAL_COUNTER(text))
        except Exception:
            pass
    if _HAS_TIKTOKEN:
        try:
            return _tiktoken_count(text)
        except Exception:
            pass
    return _approx_token_count(text)


# ──────────────────────────────────────────────────────────────────────────────
# Env helpers
# ──────────────────────────────────────────────────────────────────────────────

def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, "").strip())
        return v if v > 0 else default
    except Exception:
        return default

def _float_env(name: str, default: float) -> float:
    try:
        v = float(os.getenv(name, "").strip())
        return v if v >= 0 else default
    except Exception:
        return default


# ──────────────────────────────────────────────────────────────────────────────
# Core logic
# ──────────────────────────────────────────────────────────────────────────────

def _defaults_for_tier(tier: RetrievalTier) -> Tuple[int, float]:
    if tier == RetrievalTier.GLOBAL:
        return (
            _int_env("TOPK_GLOBAL", 6),
            _float_env("RERANK_MIN_SCORE_GLOBAL", 0.35),
        )
    if tier == RetrievalTier.CONTEXT:
        return (
            _int_env("TOPK_CONTEXT", 6),
            _float_env("RERANK_MIN_SCORE_CONTEXT", 0.35),
        )
    if tier == RetrievalTier.PROJECT_DOCS:
        return (
            _int_env("TOPK_PROJECT_DOCS", 6),
            _float_env("RERANK_MIN_SCORE_PROJECT_DOCS", 0.35),
        )
    if tier == RetrievalTier.CODE:
        return (
            _int_env("TOPK_CODE", 6),
            _float_env("RERANK_MIN_SCORE_CODE", 0.35),
        )
    return (6, 0.35)


def _normalize(scores: Sequence[float]) -> List[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo <= 1e-12:
        # Avoid div-by-zero; map all to 1.0 if there was any score at all
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def _assemble_snippet_header(path: str, tier: RetrievalTier, idx: int) -> str:
    return f"\n--- [source:{tier.value} #{idx+1}] {path} ---\n"


def _apply_threshold(matches: List[Match], min_score: float) -> List[Match]:
    return [m for m in matches if m["score"] >= min_score]


def _budgeted_concat(snippets: List[Tuple[str, str, RetrievalTier]], max_tokens: int) -> Tuple[str, List[int]]:
    """Concatenate with budget; returns (context, included_indices)."""
    out: List[str] = []
    used_indices: List[int] = []
    running = 0
    for i, (path, snippet, tier) in enumerate(snippets):
        piece = _assemble_snippet_header(path, tier, i) + snippet.strip() + "\n"
        cost = count_tokens(piece)
        if running + cost > max_tokens:
            continue
        out.append(piece)
        used_indices.append(i)
        running += cost
    return ("".join(out).strip(), used_indices)


def build_context(req: ContextRequest, cfg: EngineConfig) -> ContextResult:
    """
    Deterministic, tiered retrieval:
      Order: GLOBAL → CONTEXT → PROJECT_DOCS → CODE
      - For each tier:
         1) retrieve Top-K
         2) normalize scores to [0,1]
         3) threshold by tier min score
      - Merge results, preserve tier labels, dedupe by path (keep best score).
      - Token-budget assemble into final context.
    """
    query = (req.query or "").strip()
    max_context_tokens = req.max_tokens or _int_env("MAX_CONTEXT_TOKENS", 2400)

    ordered_tiers = [
        RetrievalTier.GLOBAL,
        RetrievalTier.CONTEXT,
        RetrievalTier.PROJECT_DOCS,
        RetrievalTier.CODE,
    ]

    all_matches: List[Match] = []
    seen_best: Dict[str, float] = {}  # path -> best normalized score
    raw_for_meta: List[float] = []
    source_paths: List[str] = []

    for tier in ordered_tiers:
        retriever = cfg.retrievers.get(tier)
        if not retriever:
            continue

        topk, min_score = _defaults_for_tier(tier)
        raw = retriever.search(query=query, k=topk)
        if not raw:
            continue

        paths, scores, snippets = zip(*raw)
        normalized = _normalize(scores)
        tier_matches: List[Match] = []
        for p, s_norm, snip in zip(paths, normalized, snippets):
            m: Match = {"path": p, "score": float(s_norm), "tier": tier.value, "snippet": snip}
            tier_matches.append(m)
            raw_for_meta.append(float(s_norm))
            source_paths.append(p)

        tier_kept = _apply_threshold(tier_matches, min_score)

        # Deduplicate by path, keep the higher score
        for m in tier_kept:
            best = seen_best.get(m["path"])
            if best is None or m["score"] > best:
                seen_best[m["path"]] = m["score"]

        all_matches.extend(tier_kept)

    # Collapse to unique best-by-path
    best_by_path: Dict[str, Match] = {}
    for m in all_matches:
        prev = best_by_path.get(m["path"])
        if (prev is None) or (m["score"] > prev["score"]):
            best_by_path[m["path"]] = m

    # Budgeted assembly
    ordered = sorted(best_by_path.values(), key=lambda m: m["score"], reverse=True)
    concat_inputs: List[Tuple[str, str, RetrievalTier]] = [
        (m["path"], m["snippet"], RetrievalTier(m["tier"])) for m in ordered
    ]
    context_str, used_idx = _budgeted_concat(concat_inputs, max_tokens=max_context_tokens)

    files_used = [ordered[i]["path"] for i in used_idx]
    max_score = max(raw_for_meta) if raw_for_meta else 0.0

    result: ContextResult = {
        "context": context_str,
        "files_used": files_used,
        "matches": ordered,  # includes snippet & score; caller can drop snippet if desired
        "meta": {
            "kb": {
                "hits": len(ordered),
                "max_score": float(max_score),
                "sources": list(dict.fromkeys(files_used)),  # stable, deduped
            }
        },
    }
    return result
