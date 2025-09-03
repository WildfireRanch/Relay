# File: agents/control_agent.py
# Purpose: Describe/acknowledge control actions in a way UIs can render even if the
#          underlying actuator is unavailable; ALWAYS include "text".
# Returns:
#   {
#     "text": "<human-readable action outcome>",
#     "answer": "<same as text>",
#     "response": { "status": "executed|queued|failed", "action": "<verb>", "params": {...}, "raw": <obj>|None },
#     "error": "<string|null>",
#     "meta": { "origin": "control", "request_id": "<id>" }
#   }

from __future__ import annotations
import asyncio, random, re
from typing import Any, Dict, Optional, List

from core.logging import log_event

# If you have an internal actuator module, import it here.
# from services.actuator import execute_action  # async (action:str, params:dict) -> dict

_PREFIX_BLOCK = re.compile(r"^\s*(?:executing|we\s+will|let'?s\s+|in\s+this\s+step)\b", re.IGNORECASE)

def _jitter(n: int, base=0.25, cap=2.5) -> float:
    return min(cap, base * (2**n)) * random.random()

def _clean(s: str) -> str:
    s = _PREFIX_BLOCK.sub("", s or "").strip()
    return re.sub(r"^\s*(?:result[:\- ]+)?", "", s, flags=re.IGNORECASE)

async def run(
    *, query: str, topics: Optional[List[str]] = None, debug: bool = False,
    request_id: Optional[str] = None, timeout_s: int = 20
) -> Dict[str, Any]:
    """
    Parse a simple verb + params from the query or topics, attempt to execute (if actuator wired),
    and ALWAYS return a human-readable 'text'.
    """
    topics = topics or []
    action = "apply"  # naive default
    params: Dict[str, Any] = {}

    # naive extraction: "turn on <thing>", "set <x>=<y>", etc.
    ql = (query or "").lower()
    if "turn on" in ql or "enable" in ql:
        action = "enable"
    elif "turn off" in ql or "disable" in ql:
        action = "disable"
    m = re.search(r"set\s+([a-z0-9_.-]+)\s*=\s*([^\s,;]+)", ql)
    if m:
        action = "set"
        params[m.group(1)] = m.group(2)

    # Optional: execute via actuator with timeout & retries
    attempts = 0
    exe_result: Dict[str, Any] | None = None
    while attempts < 2:
        attempts += 1
        try:
            async with asyncio.timeout(timeout_s):
                # if you have an actuator, call it here:
                # exe_result = await execute_action(action, params)
                exe_result = {"ok": True, "echo": {"action": action, "params": params}}
            break
        except asyncio.TimeoutError:
            if attempts >= 2: break
            await asyncio.sleep(_jitter(attempts))
        except Exception as ex:
            if attempts >= 2: break
            await asyncio.sleep(_jitter(attempts))

    ok = bool(exe_result and exe_result.get("ok"))
    status = "executed" if ok else "queued" if exe_result is None else "failed"
    summary = _clean(f"{action} {params or ''}".strip()) or "control action"

    out = {
        "text": f"{summary} — {status}.",
        "answer": f"{summary} — {status}.",
        "response": {"status": status, "action": action, "params": params, "raw": exe_result if debug else None},
        "error": None if ok else ("timeout" if exe_result is None else "failed"),
        "meta": {"origin": "control", "request_id": request_id},
    }
    log_event("control_agent_reply", {"request_id": request_id, "status": status, "action": action})
    return out
