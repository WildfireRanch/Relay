# File: planner_agent.py
# Directory: agents
# Purpose: Orchestrates LLM planning for /ask; returns a structured JSON "plan"
#          with an optional `final_answer` for definition-style queries.
#
# Upstream:
#   - ENV (required): OPENAI_API_KEY
#   - ENV (optional):
#       PLANNER_MODEL         (default "gpt-4o")
#       PLANNER_MAX_TOKENS    (default 800)
#       PLANNER_TEMPERATURE   (default 0.2)
#       PLANNER_TIMEOUT_S     (default 45)
#       PLANNER_MAX_RETRIES   (default 3)  # logical retries here (not httpx transport)
#       OPENAI_MAX_RETRIES    (fallback for PLANNER_MAX_RETRIES if set)
#   - Imports: asyncio, json, os, uuid, typing, openai, utils.openai_client, core.logging
#
# Downstream:
#   - agents.mcp_agent (calls PlannerAgent.ask)
#
# Contents:
#   - PlannerAgent
#   - planner_agent (singleton)

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from typing import Any, Dict, Optional

from openai import APIError as OpenAIError
from core.logging import log_event
from utils.openai_client import create_openai_client

# ---- Model / generation config ---------------------------------------------------------------

MODEL = os.getenv("PLANNER_MODEL", "gpt-4o")
MAX_OUT_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "800"))
TEMPERATURE = float(os.getenv("PLANNER_TEMPERATURE", "0.2"))
REQUEST_TIMEOUT_S = int(os.getenv("PLANNER_TIMEOUT_S", "45"))
MAX_RETRIES = int(os.getenv("PLANNER_MAX_RETRIES", os.getenv("OPENAI_MAX_RETRIES", "3")))

_openai = create_openai_client()

# System prompt:
#  - STRICT JSON (no markdown)
#  - Definition fast-path via `final_answer` must be used when applicable
SYSTEM_PROMPT = (
    "You are the Planner inside the Relay system. Produce a concise JSON object only.\n\n"
    "Rules:\n"
    '- Return strictly valid JSON (no markdown, no commentary).\n'
    '- Keys:\n'
    '  "objective": str,\n'
    '  "steps": [{"type": "analysis|action|docs|control", "summary": str}],\n'
    '  "recommendation": str,\n'
    '  "route": "echo" | "codex" | "docs" | "control".\n'
    "- If the user question is a DEFINITION-STYLE prompt (starts with what/who/define/describe) "
    "AND the CONTEXT contains descriptive information (Overview/Definition/Summary), then:\n"
    "    • Populate \"final_answer\" with a concise 2–4 sentence factual answer.\n"
    "    • Prefer a direct answer over rephrasing the question.\n"
    "    • Set route to \"echo\".\n"
    "- Keep plans short and executable; do not write code."
)

# ---- Helpers ---------------------------------------------------------------------------------


def _coerce_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort extraction of the first JSON object from a text blob. Returns dict or None."""
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
    except Exception:
        pass
    return None


_DEFN_PREFIXES = ("what is", "who is", "define ", "describe ")


def _is_definitional(q: str) -> bool:
    ql = (q or "").strip().lower()
    return ql.startswith(_DEFN_PREFIXES)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _extract_definition_from_context(query: str, context: str, max_chars: int = 550) -> Optional[str]:
    """
    Deterministic fallback: if the model doesn't give final_answer but the query is definitional
    and the context likely contains a definition, synthesize 2–4 sentences from context.
    Heuristics:
      - Prefer a paragraph that contains the main noun phrase from the query (first 3 words)
      - Else, take the first non-empty paragraph
      - Return up to ~2–4 sentences (<= max_chars)
    """
    if not context:
        return None

    # Rough noun phrase from query: first 3 words
    q_words = [w for w in re.sub(r"[^a-zA-Z0-9\s\-_/]", " ", (query or "")).split() if w]
    key = " ".join(q_words[:3]).lower() if q_words else ""

    # Split context into paragraphs, then pick a candidate
    paras = [p.strip() for p in context.split("\n\n") if p.strip()]
    cand = None
    if key:
        for p in paras:
            if key in p.lower():
                cand = p
                break
    if not cand and paras:
        cand = paras[0]

    if not cand:
        return None

    # Trim to 2–4 sentences
    sents = _SENTENCE_SPLIT.split(cand)
    sents = [s.strip() for s in sents if s.strip()]
    if not sents:
        return None
    take = sents[:4]
    out = " ".join(take).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    # Must look like an answer, not a restatement
    if any(out.lower().startswith(p) for p in _DEFN_PREFIXES):
        return None
    return out or None


class PlannerAgent:
    async def _call_llm(self, messages: list[dict]) -> str:
        """
        Invoke OpenAI with JSON mode and logical retries.
        Retries backoff: 1s, 2s, 4s (configurable via MAX_RETRIES).
        """
        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await _openai.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_OUT_TOKENS,
                    response_format={"type": "json_object"},
                    timeout=REQUEST_TIMEOUT_S,  # per-request timeout (client also has timeouts)
                )
                content = (resp.choices[0].message.content or "").strip()
                if not content:
                    raise OpenAIError("Empty content from model")
                return content
            except Exception as e:
                last_err = e
                wait = min(8, 2 ** (attempt - 1))
                log_event("planner_llm_retry", {"attempt": attempt, "wait_s": wait, "error": str(e)})
                await asyncio.sleep(wait)
        # Exhausted retries
        raise OpenAIError(f"Planner LLM failed after {MAX_RETRIES} attempts: {last_err}")

    async def ask(self, query: str, context: str) -> Dict[str, Any]:
        """
        Build a plan for the given query using the provided (possibly-truncated) context.

        Returns a dict with at least:
          { "objective": str, "steps": [], "recommendation": str, "route": "echo|codex|docs|control",
            "plan_id": str, ["final_answer": str]? }
        """
        plan_id = str(uuid.uuid4())
        is_def = _is_definitional(query)

        # Add a tiny, explicit hint in the USER content for definition queries
        def_hint = (
            "\n\nINSTRUCTION: If this is a definition-style question and the CONTEXT contains a definition, "
            "populate final_answer with a concise 2–4 sentence factual answer and set route to \"echo\"."
            if is_def else ""
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"QUESTION:\n{query}\n\nCONTEXT:\n{context or '[none]'}{def_hint}"},
        ]

        try:
            raw = await self._call_llm(messages)
            log_event("planner_response_raw", {"plan_id": plan_id, "sample": raw[:800]})

            # Parse with strict JSON first, then coerce if needed
            try:
                plan = json.loads(raw)
            except Exception:
                plan = _coerce_json_object(raw)

            if not isinstance(plan, dict):
                log_event("planner_parse_error", {"plan_id": plan_id, "head": raw[:1200]})
                plan = {"objective": "[invalid JSON from model]", "steps": [], "recommendation": "", "route": "echo"}

            # Minimal schema normalization
            plan.setdefault("objective", "")
            plan.setdefault("steps", [])
            plan.setdefault("recommendation", "")
            plan.setdefault("route", "echo")

            # Optional fast-path (when present, Echo will surface it as the direct answer)
            if "final_answer" in plan and isinstance(plan["final_answer"], str):
                plan["final_answer"] = plan["final_answer"].strip()

            # If still no final_answer but this is definitional and context has a definition,
            # synthesize deterministically to prevent parroting.
            if is_def and not plan.get("final_answer"):
                extracted = _extract_definition_from_context(query, context)
                if extracted:
                    plan["final_answer"] = extracted
                    plan["route"] = "echo"
                    log_event("planner_final_answer_synthesized", {"plan_id": plan_id, "chars": len(extracted)})

            # Trim step summaries to keep logs/prompts tidy
            for s in plan.get("steps", []):
                if isinstance(s, dict) and isinstance(s.get("summary"), str):
                    s["summary"] = s["summary"][:300]

            plan["plan_id"] = plan.get("plan_id") or plan_id
            return plan

        except Exception as e:
            # Safe failure: return an echo-route plan so the MCP can still answer
            log_event("planner_failed", {"plan_id": plan_id, "error": str(e)})
            return {
                "objective": "[planner failed]",
                "steps": [],
                "recommendation": "",
                "route": "echo",
                "plan_id": plan_id,
            }


# Export singleton (imported by agents.mcp_agent)
planner_agent = PlannerAgent()
