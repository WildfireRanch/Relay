# ──────────────────────────────────────────────────────────────────────────────
# File: core/context_engine.py
# Purpose: Pure context engine service with deterministic inputs/outputs.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, TypedDict

__all__ = [
    "RetrievalTier",
    "Match",
    "KBMeta",
    "ContextResult",
    "TokenCounter",
    "ContextRequest",
    "TierConfig",
    "EngineConfig",
    "Retriever",
    "ContextEngine",
    "build_context",
]

try:  # Attempt to use real tokenizers when available.
    import tiktoken  # type: ignore
    _HAS_TIKTOKEN = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_TIKTOKEN = False


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


TokenCounter = Callable[[str], int]


def _approx_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _tiktoken_count(text: str, model: str = "gpt-4o") -> int:
    try:
        enc = tiktoken.encoding_for_model(model)  # type: ignore
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")  # type: ignore
    return len(enc.encode(text))  # type: ignore


def _default_token_counter(text: str) -> int:
    if _HAS_TIKTOKEN:
        try:
            return _tiktoken_count(text)
        except Exception:
            pass
    return _approx_token_count(text)


@dataclass(frozen=True)
class ContextRequest:
    """Validated request envelope consumed by the engine."""

    query: str
    corr_id: Optional[str] = None
    max_tokens: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", (self.query or "").strip())
        corr_val = (self.corr_id or "").strip()
        object.__setattr__(self, "corr_id", corr_val or None)
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive when provided")


@dataclass(frozen=True)
class TierConfig:
    """Tier-specific retrieval knobs."""

    top_k: int = 6
    min_score: float = 0.35

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be > 0")
        if not (0.0 <= self.min_score <= 1.0):
            raise ValueError("min_score must be between 0 and 1")


@dataclass(frozen=True)
class EngineConfig:
    """Pure configuration required to assemble context."""

    retrievers: Mapping[RetrievalTier, "Retriever"]
    tier_overrides: Mapping[RetrievalTier, TierConfig] = field(default_factory=dict)
    default_tier: TierConfig = field(default_factory=TierConfig)
    max_context_tokens: int = 2400
    token_counter: Optional[TokenCounter] = None

    def __post_init__(self) -> None:
        if self.max_context_tokens <= 0:
            raise ValueError("max_context_tokens must be > 0")

        retriever_map: Dict[RetrievalTier, Retriever] = {
            tier: retriever
            for tier, retriever in (self.retrievers or {}).items()
            if retriever is not None
        }
        object.__setattr__(self, "retrievers", retriever_map)

        overrides: Dict[RetrievalTier, TierConfig] = {}
        for tier, cfg in (self.tier_overrides or {}).items():
            overrides[tier] = cfg if isinstance(cfg, TierConfig) else TierConfig(**dict(cfg))
        object.__setattr__(self, "tier_overrides", overrides)

        counter = self.token_counter or _default_token_counter
        object.__setattr__(self, "token_counter", counter)


class Retriever:
    """Interface every tier adapter must implement."""

    def search(self, query: str, k: int) -> List[Tuple[str, float, str]]:  # pragma: no cover
        raise NotImplementedError


def _normalize(scores: Sequence[float]) -> List[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo <= 1e-12:
        # Degenerate case: identical scores → all count as strongest
        return [1.0 for _ in scores]
    # Clamp defensively in case of float funkiness
    out = [(s - lo) / (hi - lo) for s in scores]
    return [0.0 if x < 0.0 else 1.0 if x > 1.0 else float(x) for x in out]


def _assemble_header(path: str, tier: RetrievalTier, idx: int) -> str:
    # One-line f-string with explicit newlines to avoid unterminated literal
    return f"\n--- [source:{tier.value} #{idx + 1}] {path} ---\n"


def _apply_threshold(matches: List[Match], min_score: float) -> List[Match]:
    return [m for m in matches if m["score"] >= min_score]


def _budgeted_concat(
    snippets: List[Tuple[str, str, RetrievalTier]],
    *,
    max_tokens: int,
    token_counter: TokenCounter,
) -> Tuple[str, List[int]]:
    out: List[str] = []
    used_indices: List[int] = []
    running = 0

    for idx, (path, snippet, tier) in enumerate(snippets):
        piece = _assemble_header(path, tier, idx) + (snippet or "").strip() + "\n"
        try:
            cost = max(0, int(token_counter(piece)))
        except Exception:
            cost = _approx_token_count(piece)
        if running + cost > max_tokens:
            continue
        out.append(piece)
        used_indices.append(idx)
        running += cost

    return "".join(out).strip(), used_indices


class ContextEngine:
    """Pure, deterministic context assembly service."""

    TIER_ORDER: Tuple[RetrievalTier, ...] = (
        RetrievalTier.GLOBAL,
        RetrievalTier.CONTEXT,
        RetrievalTier.PROJECT_DOCS,
        RetrievalTier.CODE,
    )

    def __init__(self, *, config: EngineConfig) -> None:
        """
        Initialize the ContextEngine.

        IMPORTANT: Uses keyword-only parameters. Must be called with named arguments:
            ContextEngine(config=my_config)
        NOT: ContextEngine(my_config)
        """
        self._config = config
        self._token_counter = config.token_counter

    def build(self, request: ContextRequest) -> ContextResult:
        """Assemble a context string deterministically from tiered retrievers.

        Pipeline:
          1) For each tier: search → sanitize → per-tier min–max normalize to [0,1].
          2) Apply tier min_score; keep highest score per path across tiers.
          3) Sort by (-score, path); greedily pack with token budget.
          4) Return context, files_used, per-hit matches, and kb meta.
        """
        query = request.query
        max_tokens = request.max_tokens or self._config.max_context_tokens

        aggregated: Dict[str, Match] = {}
        meta_scores: List[float] = []

        for tier in self.TIER_ORDER:
            retriever = self._config.retrievers.get(tier)
            if retriever is None:
                continue

            tier_cfg = self._config.tier_overrides.get(tier, self._config.default_tier)
            raw_results = self._safe_search(retriever, query, tier_cfg.top_k)
            if not raw_results:
                continue

            sanitized = self._sanitize(raw_results)
            if not sanitized:
                continue

            normalized = _normalize([score for _, score, _ in sanitized])
            tier_matches: List[Match] = []

            for (path, _score, snippet), norm_score in zip(sanitized, normalized):
                match: Match = {
                    "path": path,
                    "score": float(norm_score),
                    "tier": tier.value,
                    "snippet": snippet,
                }
                tier_matches.append(match)
                meta_scores.append(float(norm_score))

            kept = _apply_threshold(tier_matches, tier_cfg.min_score)
            for match in kept:
                prev = aggregated.get(match["path"])
                if prev is None or match["score"] > prev["score"]:
                    aggregated[match["path"]] = match

        ordered = sorted(
            aggregated.values(),
            key=lambda m: (-m["score"], m["path"]),
        ) if aggregated else []

        concat_inputs = [
            (m["path"], m["snippet"], RetrievalTier(m["tier"]))
            for m in ordered
        ]

        context_text, used_indices = _budgeted_concat(
            concat_inputs,
            max_tokens=max_tokens,
            token_counter=self._token_counter,
        )

        files_used = [ordered[i]["path"] for i in used_indices] if used_indices else []
        kb_sources = list(dict.fromkeys(files_used))
        max_score = max(meta_scores) if meta_scores else 0.0

        result: ContextResult = {
            "context": context_text,
            "files_used": files_used,
            "matches": ordered,
            "meta": {
                "kb": {
                    "hits": len(ordered),
                    "max_score": float(max_score),
                    "sources": kb_sources,
                }
            },
        }
        return result

    @staticmethod
    def _safe_search(retriever: "Retriever", query: str, top_k: int) -> List[Tuple[str, float, str]]:
        try:
            return list(retriever.search(query=query, k=top_k) or [])
        except TypeError:  # accommodate legacy call signatures
            return list(retriever.search(query, top_k) or [])  # type: ignore[arg-type]
        except Exception:
            return []

    @staticmethod
    def _sanitize(raw: Iterable[Tuple[object, object, object]]) -> List[Tuple[str, float, str]]:
        sanitized: List[Tuple[str, float, str]] = []
        for item in raw:
            if not isinstance(item, tuple) or len(item) < 3:
                continue
            path, score, snippet = item[:3]
            path_str = str(path or "").strip()
            if not path_str:
                continue
            try:
                score_val = float(score)
            except (TypeError, ValueError):
                continue
            snippet_str = str(snippet or "")
            sanitized.append((path_str, score_val, snippet_str))
        return sanitized


def build_context(req: ContextRequest, cfg: EngineConfig) -> ContextResult:
    """Public entry point retained for compatibility with existing callers."""

    engine = ContextEngine(config=cfg)
    return engine.build(req)
