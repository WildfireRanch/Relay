# File: services/token_budget.py
# Directory: services
# Purpose: Deterministic token budgeting and truncation utilities for prompt assembly.
#
# Overview:
# - Estimator: uses tiktoken if available; otherwise a fast heuristic (~4 chars/token).
# - Tier budgets: global/project_docs/code/etc caps enforced by tokens and item count.
# - Truncation: hard clip by tokens; optional extractive "summary" (first N sentences).
#
# Env (optional):
#   MODEL_TOKENS_PER_REQ       (default "8000")    # hard cap for final prompt
#   BUDGET_GLOBAL_TOKENS       (default "800")     # per-tier caps
#   BUDGET_CONTEXT_TOKENS      (default "1200")
#   BUDGET_DOCS_TOKENS         (default "2400")
#   BUDGET_CODE_TOKENS         (default "1600")
#   MAX_ITEMS_GLOBAL           (default "2")
#   MAX_ITEMS_CONTEXT          (default "4")
#   MAX_ITEMS_DOCS             (default "8")
#   MAX_ITEMS_CODE             (default "6")

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Tuple, Dict, Any

# Optional: tiktoken for accurate token estimation
try:
    import tiktoken  # type: ignore
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover
    _ENC = None


# ── Tunables ────────────────────────────────────────────────────────────────
MODEL_TOKENS_PER_REQ = int(os.getenv("MODEL_TOKENS_PER_REQ", "8000"))

BUDGET_GLOBAL_TOKENS  = int(os.getenv("BUDGET_GLOBAL_TOKENS",  "800"))
BUDGET_CONTEXT_TOKENS = int(os.getenv("BUDGET_CONTEXT_TOKENS", "1200"))
BUDGET_DOCS_TOKENS    = int(os.getenv("BUDGET_DOCS_TOKENS",    "2400"))
BUDGET_CODE_TOKENS    = int(os.getenv("BUDGET_CODE_TOKENS",    "1600"))

MAX_ITEMS_GLOBAL  = int(os.getenv("MAX_ITEMS_GLOBAL",  "2"))
MAX_ITEMS_CONTEXT = int(os.getenv("MAX_ITEMS_CONTEXT", "4"))
MAX_ITEMS_DOCS    = int(os.getenv("MAX_ITEMS_DOCS",    "8"))
MAX_ITEMS_CODE    = int(os.getenv("MAX_ITEMS_CODE",    "6"))


# ── Token utilities ─────────────────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    """Estimate tokens; prefer tiktoken, fallback to ~4 chars/token heuristic."""
    if not text:
        return 0
    if _ENC:
        try:
            return len(_ENC.encode(text))
        except Exception:
            pass
    # Heuristic: 1 token ≈ 4 chars, but clamp to [1, len/2]
    n = max(1, int(len(text) / 4))
    return min(n, len(text) // 2 or 1)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Hard truncate text to fit token limit (approximate but safe)."""
    if max_tokens <= 0 or not text:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text
    # Simple binary search on character count to fit target tokens
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        cand = text[:mid]
        if estimate_tokens(cand) <= max_tokens:
            lo = mid + 1
        else:
            hi = mid
    out = text[:max(0, lo - 1)]
    return out.rstrip()


def first_n_sentences(text: str, n: int = 3) -> str:
    """Extractive-lite summary: first N sentences (naive punctuation split)."""
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:max(1, n)]).strip()


# ── Tier budgeting ──────────────────────────────────────────────────────────
@dataclass
class TierSpec:
    name: str
    token_cap: int
    item_cap: int


DEFAULT_TIERS: Dict[str, TierSpec] = {
    "global":       TierSpec("global",       BUDGET_GLOBAL_TOKENS,  MAX_ITEMS_GLOBAL),
    "context":      TierSpec("context",      BUDGET_CONTEXT_TOKENS, MAX_ITEMS_CONTEXT),
    "project_docs": TierSpec("project_docs", BUDGET_DOCS_TOKENS,    MAX_ITEMS_DOCS),
    "code":         TierSpec("code",         BUDGET_CODE_TOKENS,    MAX_ITEMS_CODE),
}


def pack_tier_chunks(
    chunks: List[str],
    tier: TierSpec,
    allow_summarize: bool = True,
    extractive_sentences: int = 3,
) -> Tuple[str, List[str]]:
    """
    Pack a list of text chunks for a tier into a single string <= token cap.
    Returns (packed_text, used_chunks).
    """
    used: List[str] = []
    if not chunks:
        return "", used

    # Respect item cap first (high relevance ordering assumed upstream)
    trimmed = chunks[: max(0, tier.item_cap)]

    acc: List[str] = []
    for chunk in trimmed:
        if not chunk:
            continue
        # If the chunk alone exceeds the tier cap, try to summarize
        if estimate_tokens(chunk) > tier.token_cap and allow_summarize:
            chunk = first_n_sentences(chunk, extractive_sentences)

        # If still too big, hard-trim chunk to fit at least something
        if estimate_tokens(chunk) > tier.token_cap:
            chunk = truncate_to_tokens(chunk, tier.token_cap // 2)

        # Try to add the chunk; if it pushes over the cap, stop
        trial = "\n\n" + chunk if acc else chunk
        if estimate_tokens("".join(acc) + trial) <= tier.token_cap:
            acc.append(trial if acc else chunk)
            used.append(chunk)
        else:
            # Try to squeeze a truncated version
            remaining = tier.token_cap - estimate_tokens("".join(acc))
            if remaining > 50:  # leave room to be useful
                squeezed = truncate_to_tokens(chunk, remaining)
                if squeezed:
                    acc.append("\n\n" + squeezed)
                    used.append(squeezed)
            break

    return "".join(acc), used
