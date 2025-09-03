# File: agents/codex_agent.py
# Purpose: Code actions (plan/patch) but ALWAYS include a short "text" summary.
# Returns:
#   {
#     "text": "<human-readable action summary>",
#     "answer": "<same as text>",
#     "response": { "action": {...}, "diff": "<unified|None>", "raw": <llm_obj>|None },
#     "error": "<string|null>",
#     "meta": { "origin": "codex", "model": "<name>", "request_id": "<id>" }
#   }

from __future__ import annotations
import asyncio, random, re
from typing import Any, Dict, List, Optional

from core.logging import log_event

try:
    from services.openai_client import chat_complete  # async
except Exception:
    chat_complete = None  # pragma: no cover

CODEX_MODEL = "gpt-4o-mini"

_PREFIX_BLOCK = re.compile(r"^\s*(?:here'?s\s+the\s+patch|we\s+will|let'?s\s+|in\s+this\s+change)\b", re.IGNORECASE)

def _jitter(n: int, base=0.25, cap=2.5) -> float:
    return min(cap, base * (2**n)) * random.random()

def _clean(s: str) -> str:
    s = _PREFIX_BLOCK.sub("", s or "").strip()
    return re.sub(r"^\s*(?:summary[:\- ]+)?", "", s, flags=re.IGNORECASE)

def _mk_summary(query: str, plan: Dict[str, Any], diff: Optional[str]) -> str:
    head = plan.get("summary") if isinstance(plan, dict) else None
    if isinstance(head, str) and head.strip():
        return _clean(head)
    if diff and isinstance(diff, str):
        return _clean(f"Proposed code change touching {min(6, diff.count('\n'))} lines.")
    return _clean(f"Proposed code action for: {query.strip()[:80]}")

async def _codex_llm(query: str, files: List[str], topics: List[str], timeout_s: int, model: str) -> Dict[str, Any]:
    if not chat_complete:
        return {"action": {"type": "plan", "summary": f"Plan for: {query[:80]}"}, "diff": None, "raw": None}
    user = f"{query.strip()}\n\nFiles: {', '.join(files[:6])}\nTopics: {', '.join(topics[:6])}"
    sys = ("Propose the minimal, safe change. Output:\n"
           "1) A one-line summary (Summary: ...)\n2) If a patch is needed, include a unified diff fenced with ```diff\n...\n```\n"
           "No preambles.")
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            async with asyncio.timeout(timeout_s):
                resp = await chat_complete(system=sys, user=user, model=model, timeout_s=timeout_s)
            text = (resp.get("text") or "").strip()
            # Naive extraction
            diff = None
            if "```diff" in text:
                try:
                    diff = text.split("```diff", 1)[1].split("```", 1)[0].strip()
                except Exception:
                    pass
            summary = None
            m = re.search(r"summary\s*:\s*(.+)", text, re.IGNORECASE)
            if m:
                summary = m.group(1).strip()
            return {"action": {"type": "plan", "summary": summary or "Proposed code action"}, "diff": diff, "raw": resp.get("raw")}
        except asyncio.TimeoutError:
            if attempts >= 3: break
            await asyncio.sleep(_jitter(attempts))
        except Exception as ex:
            msg = str(ex).lower()
            if not any(k in msg for k in ("timeout", "rate limit", "temporar", "unavailable")) or attempts >= 3:
                break
            await asyncio.sleep(_jitter(attempts))
    return {"action": {"type": "plan", "summary": "Code analysis failed"}, "diff": None, "raw": None}

async def run(
    *, query: str, files: Optional[List[str]] = None, topics: Optional[List[str]] = None,
    debug: bool = False, request_id: Optional[str] = None, timeout_s: int = 40
) -> Dict[str, Any]:
    files, topics = files or [], topics or []
    try:
        res = await _codex_llm(query, files, topics, timeout_s, CODEX_MODEL)
        text = _mk_summary(query, res.get("action", {}), res.get("diff"))
        out = {
            "text": text,
            "answer": text,
            "response": {"action": res.get("action"), "diff": res.get("diff"), "raw": res.get("raw") if debug else None},
            "error": None,
            "meta": {"origin": "codex", "model": CODEX_MODEL, "request_id": request_id},
        }
        log_event("codex_agent_reply", {"request_id": request_id, "has_diff": bool(res.get("diff"))})
        return out
    except Exception as ex:
        text = "Code action failed."
        return {
            "text": text,
            "answer": text,
            "response": {"action": {"type": "error"}, "diff": None},
            "error": str(ex),
            "meta": {"origin": "codex", "model": CODEX_MODEL, "request_id": request_id},
        }
