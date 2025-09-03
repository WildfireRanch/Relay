# File: agents/codex_agent.py
# Purpose: Generate safe, minimal code actions (plan and/or patch) and ALWAYS
#          return a short human-readable "text" summary suitable for the UI.
#
# Contract (output):
# {
#   "text": "<human-readable action summary>",
#   "answer": "<same as text>",
#   "response": {
#       "action": { "type": "plan" | "patch" | "error", "summary": "<string>" },
#       "diff": "<unified diff text | None>",
#       "raw": <opaque LLM response | None>   # only when debug=True
#   },
#   "error": "<string | None>",
#   "meta": { "origin": "codex", "model": "<name>", "request_id": "<id|None>" }
# }
#
# Notes:
# - Designed to be import-safe in production (no SyntaxErrors at import-time).
# - Avoids backslashes within f-string expressions to prevent parser errors.
# - Diff parsing is defensive (supports fenced ```diff blocks or plain unified diffs).
# - The summary is guaranteed non-empty and UI-safe.
# - LLM timeouts and transient errors are retried with jittered backoff.

from __future__ import annotations

import os
import re
import asyncio
import random
from typing import Any, Dict, List, Optional, Tuple

from core.logging import log_event

# Optional, async LLM client (must provide a `chat_complete` coroutine).
# Expected signature (compat):
#   await chat_complete(system=str, user=str, model=str, timeout_s=int) -> Dict[str, Any]
try:
    from services.openai_client import chat_complete  # async
except Exception:  # pragma: no cover
    chat_complete = None  # type: ignore


# ------------------------------ Configuration ---------------------------------

# Allow overriding via environment, fall back to a small/cheap capable model
CODEX_MODEL = os.getenv("CODEX_MODEL", "gpt-4o-mini")

# Safety caps
MAX_SUMMARY_LEN = 200            # hard cap for UI summary text
MAX_DIFF_CHARS = 50_000          # keep responses bounded
MAX_DIFF_LINES = 2_000

# Regexes for light cleanup and parsing
_PREFIX_BLOCK = re.compile(
    r"^\s*(?:here'?s\s+the\s+patch|we\s+will|let'?s\s+|in\s+this\s+change)\b",
    re.IGNORECASE,
)

SUMMARY_LINE = re.compile(r"^\s*summary\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)

# Matches fenced diff blocks: ```diff ... ```
FENCED_DIFF = re.compile(r"```diff\s*\n(.*?)\n```", re.IGNORECASE | re.DOTALL)

# Very loose unified-diff scent (in case model forgets fences)
UNIFIED_DIFF_HINT = re.compile(
    r"(?:(?:^|\n)diff\s--git[^\n]*\n.+?|\n---\s[^\n]*\n\+\+\+\s[^\n]*\n)",
    re.IGNORECASE | re.DOTALL,
)


# ------------------------------- Utilities ------------------------------------

def _jitter(attempt: int, base: float = 0.25, cap: float = 2.5) -> float:
    """Exponential backoff with jitter."""
    return min(cap, base * (2 ** attempt)) * random.random()


def _clean(text: str) -> str:
    """Mildly normalize a UI string: trim, drop generic preambles, squash 'Summary:'."""
    s = (text or "").strip()
    if not s:
        return ""
    s = _PREFIX_BLOCK.sub("", s).strip()
    s = re.sub(r"^\s*(?:summary[:\-\s]+)", "", s, flags=re.IGNORECASE).strip()
    # collapse internal excessive whitespace while preserving newlines minimally
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s


def _cap(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _coerce_text(resp: Dict[str, Any]) -> str:
    """
    Try to extract a primary text field from a variety of possible response shapes.
    Compatible with common OpenAI-like wrappers.
    """
    if not isinstance(resp, dict):
        return ""
    # Preferred keys
    for key in ("text", "content"):
        if isinstance(resp.get(key), str):
            return resp[key]

    # OpenAI chat-like shape
    choices = resp.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict):
            c = msg.get("content")
            if isinstance(c, str):
                return c

    # Fallback: stringify a few known keys
    return str(resp)


def _extract_diff_and_summary(blob: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract `summary` (one-liner) and `diff` (unified) from the LLM text blob.
    - Summary: from a line like 'Summary: ...' (first match wins).
    - Diff: fenced ```diff blocks``` preferred; otherwise attempt to detect a unified diff.
    """
    if not blob or not isinstance(blob, str):
        return None, None

    text = blob.strip()

    # Summary
    summary: Optional[str] = None
    m = SUMMARY_LINE.search(text)
    if m:
        summary = _clean(_cap(m.group(1).strip(), MAX_SUMMARY_LEN))

    # Diff: fenced block first
    diff: Optional[str] = None
    fm = FENCED_DIFF.search(text)
    if fm:
        diff = fm.group(1).strip()
    else:
        # heuristic: look for unified diff scent, then take from first scent to the end
        um = UNIFIED_DIFF_HINT.search(text)
        if um:
            start = um.start()
            diff = text[start:].strip()

    # Normalize/cap diff if present
    if diff:
        # strip accidental triple-backticks inside
        diff = re.sub(r"```+", "", diff).strip()
        # cap by lines then chars
        lines = diff.splitlines()
        if len(lines) > MAX_DIFF_LINES:
            diff = "\n".join(lines[:MAX_DIFF_LINES]) + "\n…"
        diff = _cap(diff, MAX_DIFF_CHARS)

    return summary, (diff if diff else None)


def _mk_summary(query: str, plan: Dict[str, Any], diff: Optional[str]) -> str:
    """
    Build a concise, UI-safe summary for a proposed code action.

    Priority:
      1) Use plan['summary'] if present and non-empty.
      2) If a diff is provided, report (capped) touched line count.
      3) Fall back to the query, then a generic message.
    """
    # 1) plan summary if available
    head = plan.get("summary") if isinstance(plan, dict) else None
    if isinstance(head, str) and head.strip():
        return _cap(_clean(head.strip()), MAX_SUMMARY_LEN)

    # 2) diff-based summary
    if isinstance(diff, str) and diff.strip():
        # IMPORTANT: do NOT put a backslash-containing literal inside an f-string expression
        # Compute outside to avoid "f-string expression part cannot include a backslash"
        line_count = diff.count("\n")
        touched = min(6, max(0, line_count))
        plural = "" if touched == 1 else "s"
        base = f"Proposed code change touching {touched} line{plural}."
        return _cap(_clean(base), MAX_SUMMARY_LEN)

    # 3) query fallback
    q = (query or "").strip()
    if q:
        return _cap(_clean(f"Proposed code action for: {q[:80]}"), MAX_SUMMARY_LEN)

    return "Proposed code action."


async def _codex_llm(
    query: str,
    files: List[str],
    topics: List[str],
    timeout_s: int,
    model: str,
    *,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """
    Call the LLM with guardrails and a hard timeout. Returns a normalized dict:
      { "action": {"type": "plan"|"patch", "summary": "<str>"},
        "diff": "<unified diff|None>",
        "raw": <opaque or None> }
    """
    # If LLM is not configured, synthesize a safe stub.
    if not chat_complete:
        stub_summary = _mk_summary(query, {"summary": f"Plan for: {query[:80]}"},
                                   diff=None)
        return {"action": {"type": "plan", "summary": stub_summary}, "diff": None, "raw": None}

    # Compose concise prompt
    sys = (
        "You are Codex, a careful code editor.\n"
        "Task: Propose the minimal, safe change.\n"
        "Output STRICTLY in this form:\n"
        "  Summary: <one-line action summary>\n"
        "  ```diff\n"
        "  <unified diff if needed; otherwise omit the fenced block>\n"
        "  ```\n"
        "Rules:\n"
        " - No preambles, no explanations.\n"
        " - Only include a diff if an actual code change is required.\n"
        " - Keep the summary concise and human-readable."
    )

    files_part = ", ".join(files[:8]) if files else "None"
    topics_part = ", ".join(topics[:8]) if topics else "None"
    user = (
        f"{query.strip()}\n\n"
        f"Files: {files_part}\n"
        f"Topics: {topics_part}"
    )

    attempts = 0
    last_err: Optional[str] = None

    while attempts < max_attempts:
        attempts += 1
        try:
            # Use asyncio timeout (Python 3.11+)
            async with asyncio.timeout(timeout_s):
                resp: Dict[str, Any] = await chat_complete(
                    system=sys, user=user, model=model, timeout_s=timeout_s
                )

            text_blob = _coerce_text(resp)
            summary, diff = _extract_diff_and_summary(text_blob)

            action_type = "patch" if diff else "plan"
            action_summary = summary or "Proposed code action"

            return {
                "action": {"type": action_type, "summary": action_summary},
                "diff": diff,
                "raw": resp,  # Caller decides whether to keep/remove in run(debug=...)
            }

        except asyncio.TimeoutError:
            last_err = f"timeout after {timeout_s}s"
        except Exception as ex:  # transient or permanent; retry a few times
            msg = str(ex).lower()
            last_err = msg
            # Only retry obvious transients
            if not any(k in msg for k in ("timeout", "rate limit", "temporar", "unavailable")):
                break

        if attempts < max_attempts:
            await asyncio.sleep(_jitter(attempts))

    # Exhausted attempts: return a failure-shaped response
    return {
        "action": {"type": "plan", "summary": "Code analysis failed"},
        "diff": None,
        "raw": {"error": last_err} if last_err else None,
    }


# ---------------------------------- Public API --------------------------------

async def run(
    *,
    query: str,
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    debug: bool = False,
    request_id: Optional[str] = None,
    timeout_s: int = 40,
) -> Dict[str, Any]:
    """
    Entry point used by the MCP/ASK pipeline.

    - Always returns a UI-friendly `text` and mirrors it to `answer`.
    - `response.raw` is included only when `debug=True` to avoid payload bloat.
    - Emits a telemetry event with basic diagnostics.
    """
    files = files or []
    topics = topics or []

    try:
        res = await _codex_llm(query, files, topics, timeout_s, CODEX_MODEL)

        # Compute final UI text using the normalized `action.summary` and `diff`
        action: Dict[str, Any] = res.get("action") or {}
        diff_text: Optional[str] = res.get("diff")
        ui_text = _mk_summary(query, action, diff_text)

        out: Dict[str, Any] = {
            "text": ui_text,
            "answer": ui_text,
            "response": {
                "action": action,
                "diff": diff_text,
                "raw": (res.get("raw") if debug else None),
            },
            "error": None,
            "meta": {
                "origin": "codex",
                "model": CODEX_MODEL,
                "request_id": request_id,
            },
        }

        # Telemetry
        log_event(
            "codex_agent_reply",
            {
                "request_id": request_id,
                "has_diff": bool(diff_text),
                "action_type": action.get("type"),
                "summary_len": len(str(action.get("summary") or "")),
            },
        )

        return out

    except Exception as ex:
        # Hard failure: make the error explicit but keep the shape stable
        err_msg = str(ex)
        fallback_text = "Code action failed."
        log_event(
            "codex_agent_error",
            {"request_id": request_id, "error": err_msg},
        )
        return {
            "text": fallback_text,
            "answer": fallback_text,
            "response": {"action": {"type": "error", "summary": "error"}, "diff": None},
            "error": err_msg,
            "meta": {
                "origin": "codex",
                "model": CODEX_MODEL,
                "request_id": request_id,
            },
        }
