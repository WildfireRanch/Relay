# File: agents/docs_agent.py
# Purpose: Analyze docs/context against a user query and produce a structured,
#          critic-reviewed summary. Robust to param mismatches and JSON coercion.

from __future__ import annotations

import asyncio
import json
import os
import re
import traceback
from typing import Any, Dict, Optional

from openai import OpenAIError
from agents.critic_agent import run_critics
from core.logging import log_event
from utils.openai_client import create_openai_client

# ── Config ──────────────────────────────────────────────────────────────────
DOCS_MODEL = os.getenv("DOCS_MODEL", "gpt-4o")
DOCS_TEMPERATURE = float(os.getenv("DOCS_TEMPERATURE", "0.4"))
DOCS_MAX_TOKENS = int(os.getenv("DOCS_MAX_TOKENS", "800"))

SYSTEM_PROMPT = """
You are an expert technical analyst. Given a user query and a longform document,
return a concise, structured JSON object that helps the user take action.

Return STRICT JSON ONLY with this schema (no markdown, no prose outside JSON):

{
  "objective": "one-sentence purpose in the user's terms",
  "steps": ["short actionable steps, 3-7 items max"],
  "recommendation": "1-3 sentence conclusion or next-step guidance"
}

Rules:
- Be specific. Use doc details only if they are relevant to the query.
- Do NOT include the entire document or large quotes.
- No markdown, no code fences, no commentary outside the JSON.
""".strip()

# Single client instance
client = create_openai_client()


# ── Helpers ─────────────────────────────────────────────────────────────────
def _coerce_json(text: str) -> Dict[str, Any]:
    """Parse JSON; if invalid, try to extract the first JSON object."""
    text = (text or "").strip()
    # Fast path
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Try to extract a JSON object via regex
    try:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                log_event("docs_agent_coercion_used", {"reason": "regex_object_extract"})
                return obj
    except Exception:
        pass

    # Last-resort minimal structure
    log_event("docs_agent_coercion_used", {"reason": "fallback_minimal"})
    return {
        "objective": "",
        "steps": [],
        "recommendation": text[:400].strip() if text else "",
    }


async def _maybe_await(x: Any) -> Any:
    return await x if asyncio.iscoroutine(x) else x


def _enforce_schema(d: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure required keys exist and are within bounds."""
    out: Dict[str, Any] = {}
    out["objective"] = str(d.get("objective", "") or "")[:400]
    steps = d.get("steps", [])
    if not isinstance(steps, list):
        steps = [str(steps)]
    steps = [str(s)[:400] for s in steps][:7]  # cap length & count
    out["steps"] = steps
    out["recommendation"] = str(d.get("recommendation", "") or "")[:800]
    return out


# ── Agent ───────────────────────────────────────────────────────────────────
class DocsAgent:
    async def analyze(
        self,
        query: str,
        context: str,
        user_id: str = "anonymous",
        **kwargs: Any,  # tolerate extra args like plan=... from MCP
    ) -> Dict[str, Any]:
        """
        Analyze document content in light of the user query.
        Returns structured JSON with critics output and meta.
        """
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Query:\n{query}\n\nDocument:\n{context}"},
            ]

            # Prefer modern JSON mode; gracefully fall back if not supported by this client version
            try:
                completion = await client.chat.completions.create(
                    model=DOCS_MODEL,
                    messages=messages,
                    temperature=DOCS_TEMPERATURE,
                    max_tokens=DOCS_MAX_TOKENS,
                    response_format={"type": "json_object"},  # new-style
                )
            except TypeError:
                completion = await client.chat.completions.create(
                    model=DOCS_MODEL,
                    messages=messages,
                    temperature=DOCS_TEMPERATURE,
                    max_tokens=DOCS_MAX_TOKENS,
                    response_format="json",  # legacy
                )

            raw = (completion.choices[0].message.content or "").strip()
            log_event("docs_agent_raw", {"q_head": query[:120], "out_head": raw[:400]})

            parsed = _coerce_json(raw)
            summary = _enforce_schema(parsed)

            # Run critics (non-fatal) with correct signature; support sync/async impls
            critics = None
            try:
                res = run_critics(plan=summary, query=query)  # may be sync or async
                critics = await _maybe_await(res)
            except Exception as crit_exc:
                log_event("docs_agent_critics_error", {"error": str(crit_exc)})

            if isinstance(critics, list):
                summary["critics"] = critics

            # High-signal log for observability
            log_event(
                "docs_agent_critique",
                {
                    "user": user_id,
                    "objective": summary.get("objective"),
                    "steps": len(summary.get("steps", [])),
                    "has_recommendation": bool(summary.get("recommendation")),
                    "critics": (len(critics) if isinstance(critics, list) else 0),
                },
            )

            # Wrap with meta for provenance
            routed = {
                "analysis": summary,
                "meta": {"origin": "docs", "model": DOCS_MODEL},
            }
            log_event("docs_agent_reply", {"user": user_id, "origin": "docs"})
            return routed

        except OpenAIError as e:
            log_event("docs_agent_error", {"error": str(e), "user_id": user_id})
            return {
                "error": "OpenAI failed to respond.",
                "meta": {"origin": "docs", "model": DOCS_MODEL},
            }

        except Exception as e:
            log_event("docs_agent_exception", {"error": str(e), "trace": traceback.format_exc()})
            return {
                "error": "Unexpected error in docs agent.",
                "meta": {"origin": "docs", "model": DOCS_MODEL},
            }


# Exported instance + function (back-compat with MCP dispatch)
docs_agent = DocsAgent()
analyze = docs_agent.analyze
