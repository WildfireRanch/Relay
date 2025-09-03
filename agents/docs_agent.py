# File: agents/docs_agent.py
# Purpose: Summarize/answer over provided files or KB and ALWAYS return stringifiable fields.
# Contract (any of these may be called): summarize(...), analyze(...), run(...), answer(...)
# Returns (stable):
#   {
#     "text": "<human-readable summary/answer>",
#     "answer": "<same as text>",
#     "response": { "summary": {...}, "sources": [...], "raw": <llm_obj>|None },
#     "error": "<string|null>",
#     "meta": { "origin": "docs", "model": "<name>", "request_id": "<id>" }
#   }

from __future__ import annotations
import asyncio, random, re
from typing import Any, Dict, List, Optional

from core.logging import log_event

try:
    from services.openai_client import chat_complete  # async
except Exception:
    chat_complete = None  # pragma: no cover

try:
    from services.kb import fetch_file_snippets  # async helper: (paths: list[str]) -> list[dict{text,source}]
except Exception:
    async def fetch_file_snippets(files: List[str]) -> List[Dict[str, str]]:
        return [{"text": f"(no kb adapter) {p}", "source": p} for p in files or []]  # safe fallback

DOCS_MODEL = "gpt-4o-mini"  # tune if desired

_PREFIX_BLOCK = re.compile(
    r"^\s*(?:what\s+is|define|understand|in\s+this\s+answer|we\s+will|here'?s\s+|"
    r"this\s+document\s+|the\s+following)\b",
    re.IGNORECASE,
)

def _jitter(n: int, base=0.25, cap=2.5) -> float:
    return min(cap, base * (2**n)) * random.random()

def _clean_lead(s: str) -> str:
    s = _PREFIX_BLOCK.sub("", s or "").strip()
    s = re.sub(r"^\s*(?:answer[:\- ]+)?", "", s, flags=re.IGNORECASE)
    return s

def _mk_text(summary: Dict[str, Any], fallback: str) -> str:
    for k in ("summary", "recommendation", "key_points", "text"):
        v = summary.get(k)
        if isinstance(v, str) and v.strip():
            return _clean_lead(v.strip())
    return _clean_lead(fallback)

async def _summarize_llm(query: str, blobs: List[Dict[str, str]], timeout_s: int, model: str) -> Dict[str, Any]:
    """Call LLM with retries; return {"summary":<str>, "sources":[...], "raw":<obj>|None}."""
    if not chat_complete:
        return {"summary": f"{query.strip()}: concise summary based on provided sources.", "sources": [b["source"] for b in blobs[:4]], "raw": None}

    prompt_lines = [query.strip(), "", "Context snippets:"]
    for b in blobs[:8]:  # cap prompt size
        prompt_lines.append(f"- {b['text'][:600]} (source: {b['source']})")
    user = "\n".join(prompt_lines)

    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            async with asyncio.timeout(timeout_s):
                resp = await chat_complete(
                    system=("Summarize crisply. No lead-ins. Include only facts supported by snippets. "
                            "If uncertain, say so tersely. End with 1–3 bullet points if helpful."),
                    user=user,
                    model=model,
                    timeout_s=timeout_s,
                )
            text = (resp.get("text") or "").strip() or "Summary not available."
            return {"summary": text, "sources": [b["source"] for b in blobs[:6]], "raw": resp.get("raw")}
        except asyncio.TimeoutError:
            if attempts >= 3: break
            await asyncio.sleep(_jitter(attempts))
        except Exception as ex:
            msg = str(ex).lower()
            if not any(k in msg for k in ("timeout", "rate limit", "temporar", "unavailable")) or attempts >= 3:
                break
            await asyncio.sleep(_jitter(attempts))
    return {"summary": "Docs analysis encountered an error.", "sources": [b["source"] for b in blobs[:4]], "raw": None}

async def _entry(query: str, files: Optional[List[str]], *, debug: bool, timeout_s: int, request_id: Optional[str]) -> Dict[str, Any]:
    files = files or []
    try:
        # 1) Gather snippets (safe even without KB adapter)
        blobs = await fetch_file_snippets(files)
        # 2) LLM summarize (or deterministic fallback)
        res = await _summarize_llm(query, blobs, timeout_s, DOCS_MODEL)
        text = _mk_text({"summary": res["summary"]}, fallback=f"{query.strip()}: concise summary.")
        out = {
            "text": text,
            "answer": text,
            "response": {"summary": {"text": res["summary"]}, "sources": res.get("sources", []), "raw": res.get("raw") if debug else None},
            "error": None,
            "meta": {"origin": "docs", "model": DOCS_MODEL, "request_id": request_id},
        }
        log_event("docs_agent_reply", {"request_id": request_id, "len": len(text)})
        return out
    except Exception as ex:
        text = "Docs analysis failed."
        return {
            "text": text,
            "answer": text,
            "response": {"summary": {"text": text}, "sources": files[:4]},
            "error": str(ex),
            "meta": {"origin": "docs", "model": DOCS_MODEL, "request_id": request_id},
        }

# Public entrypoints (any name the orchestrator calls should resolve)
async def summarize(*, query: str, files: Optional[List[str]] = None, debug: bool = False, request_id: Optional[str] = None, timeout_s: int = 30) -> Dict[str, Any]:
    return await _entry(query, files, debug=debug, timeout_s=timeout_s, request_id=request_id)

async def analyze(**kw):   return await summarize(**kw)
async def answer(**kw):    return await summarize(**kw)
async def run(**kw):       return await summarize(**kw)
