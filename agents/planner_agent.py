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
#       PLANNER_MAX_RETRIES   (default 3)  # logical retries here (not transport)
#       OPENAI_MAX_RETRIES    (fallback for PLANNER_MAX_RETRIES if set)
#   - Imports: asyncio, json, os, uuid, typing, core.logging, utils.openai_client
#
# Downstream:
#   - agents.mcp_agent (calls PlannerAgent.ask)
#
# Notes:
#   - We NEVER allow a parrot-y final_answer. We gate model FA quality
#     and synthesize deterministically from context when needed.
#   - We strip placeholder/heading lines from context before using them.
#   - Strict JSON (coerced if needed), route validation, defensive caps, and rich _diag.

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from typing import Any, Dict, Optional, List

from openai import APIError as OpenAIError
from core.logging import log_event
from utils.openai_client import create_openai_client

# ── Model / generation config ────────────────────────────────────────────────

MODEL = os.getenv("PLANNER_MODEL", "gpt-4o")
MAX_OUT_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "800"))
TEMPERATURE = float(os.getenv("PLANNER_TEMPERATURE", "0.2"))
REQUEST_TIMEOUT_S = int(os.getenv("PLANNER_TIMEOUT_S", "45"))
MAX_RETRIES = int(os.getenv("PLANNER_MAX_RETRIES", os.getenv("OPENAI_MAX_RETRIES", "3")))

# Output caps (defensive)
MAX_FIELD_CHARS = 800
MAX_FINAL_ANSWER_CHARS = 600

ALLOWED_ROUTES = {"echo", "codex", "docs", "control"}

_openai = create_openai_client()

# System prompt:
#  - STRICT JSON (no markdown)
#  - Definition fast-path via `final_answer` must be used when applicable
SYSTEM_PROMPT = (
    "You are the Planner inside the Relay system. Produce a concise JSON object only.\n\n"
    "Rules:\n"
    '- Return strictly valid JSON (no markdown, no commentary).\n'
    '- Keys:\n'
    '  \"objective\": str,\n'
    '  \"steps\": [{\"type\": \"analysis|action|docs|control\", \"summary\": str}],\n'
    '  \"recommendation\": str,\n'
    '  \"route\": \"echo\" | \"codex\" | \"docs\" | \"control\".\n'
    "- If the user question is a DEFINITION-STYLE prompt (starts with what/who/define/describe/explain) "
    "AND the CONTEXT contains an actual definition, then:\n"
    "    • Populate \"final_answer\" with a concise 2–4 sentence factual answer (avoid rephrasing the question).\n"
    "    • Set route to \"echo\".\n"
    "- Keep plans short and executable; do not write code."
)

# ── Helpers ─────────────────────────────────────────────────────────────────

_FENCE_PAT = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_DEFN_PREFIXES = ("what is", "who is", "define", "describe", "explain")
# Anything that starts like the question itself is likely a parrot
_PARROT_PAT = re.compile(r"^\s*(what\s+is|who\s+is|define|describe|explain)\b", re.I)
# Lines we never want to treat as source: headings/empties/placeholders
_BAD_SUMMARY_MARKERS = (
    "project summary not available",
    "global project context not available",
    "semantic retrieval unavailable",
    "[semantic retrieval unavailable]",
)
_HEADING_PAT = re.compile(r"^\s*#{1,6}\s*")  # markdown headings

def _clean_text(t: str, cap: int = MAX_FINAL_ANSWER_CHARS) -> str:
    """Strip fences, collapse whitespace, cap length."""
    if not t:
        return ""
    t = _FENCE_PAT.sub("", t).strip()
    t = " ".join(t.split())
    if len(t) > cap:
        t = t[:cap].rstrip() + "…"
    return t

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

def _is_definitional(q: str) -> bool:
    ql = (q or "").strip().lower()
    ql = ql.rstrip(" ?!.:")
    return any(ql.startswith(p) for p in _DEFN_PREFIXES)

def _looks_like_definition(s: str) -> bool:
    """A minimal bar for definition quality: contains is a/an and not a pure restatement."""
    ls = (s or "").strip().lower()
    if not ls:
        return False
    if _PARROT_PAT.match(ls):
        return False
    return (" is a " in ls) or (" is an " in ls)

def _filter_context_lines(context: str) -> List[str]:
    """Remove headings/empties/placeholders to avoid polluting definition synth."""
    out: List[str] = []
    for ln in (context or "").splitlines():
        ls = ln.strip()
        lsl = ls.lower()
        if not ls:
            continue
        if _HEADING_PAT.match(ls):
            continue
        if any(m in lsl for m in _BAD_SUMMARY_MARKERS):
            continue
        out.append(ls)
    return out

def _extract_definition_from_context(
    query: str,
    context: str,
    max_chars: int = MAX_FINAL_ANSWER_CHARS
) -> Optional[str]:
    """
    Deterministic fallback: if the model doesn't give final_answer but the query is definitional
    and the context likely contains a definition, synthesize 2–4 sentences from context.
    Heuristics:
      - Filter out headings/placeholders first.
      - Prefer the first paragraph containing the main noun phrase (first 3 tokens of the query).
      - Else, the first non-empty paragraph.
      - Return up to 2–4 sentences (<= max_chars).
      - Reject if the result looks like a parrot / fails definition check.
    """
    if not context:
        return None

    lines = _filter_context_lines(context)
    if not lines:
        return None

    clean_ctx = "\n".join(lines)
    paras = [p.strip() for p in re.split(r"\n\s*\n", clean_ctx) if p.strip()]
    if not paras:
        paras = [clean_ctx.strip()] if clean_ctx.strip() else []

    # key phrase from query (first 3 tokens)
    tokens = [w for w in re.sub(r"[^a-zA-Z0-9\s\-_/]", " ", (query or "")).split() if w]
    key = " ".join(tokens[:3]).lower() if tokens else ""

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

    sents = [s.strip() for s in _SENTENCE_SPLIT.split(cand) if s.strip()]
    if not sents:
        return None
    out = " ".join(sents[:4]).strip()
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    out = _clean_text(out)
    if not _looks_like_definition(out):
        return None
    return out or None

# ── Agent ───────────────────────────────────────────────────────────────────

class PlannerAgent:
    async def _call_llm(self, messages: list[dict]) -> str:
        """
        Invoke OpenAI with JSON mode and logical retries.
        Backoff: 1s, 2s, 4s (capped at 8s per attempt).
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
                    timeout=REQUEST_TIMEOUT_S,
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

        # Small, explicit instruction so the model knows when to use final_answer
        def_hint = (
            "\n\nINSTRUCTION: If this is a definition-style question and the CONTEXT contains a definition, "
            "populate final_answer with a concise 2–4 sentence factual answer (not a restatement) and set route to \"echo\"."
            if is_def else ""
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"QUESTION:\n{query}\n\nCONTEXT:\n{context or '[none]'}{def_hint}"},
        ]

        coercion_used = False
        parrot_rejected = False
        try:
            raw = await self._call_llm(messages)
            log_event("planner_response_raw", {"plan_id": plan_id, "sample": raw[:800]})

            # Parse JSON, then coerce if needed
            try:
                plan = json.loads(raw)
            except Exception:
                plan = _coerce_json_object(raw)
                coercion_used = True

            if not isinstance(plan, dict):
                log_event("planner_parse_error", {"plan_id": plan_id, "head": raw[:1200]})
                plan = {"objective": "[invalid JSON from model]", "steps": [], "recommendation": "", "route": "echo"}

            # Minimal schema normalization
            plan.setdefault("objective", "")
            plan.setdefault("steps", [])
            plan.setdefault("recommendation", "")
            plan.setdefault("route", "echo")

            # Validate route
            route = str(plan.get("route") or "echo").strip().lower()
            plan["route"] = route if route in ALLOWED_ROUTES else "echo"

            # Cap noisy fields
            if isinstance(plan["objective"], str):
                plan["objective"] = _clean_text(plan["objective"], MAX_FIELD_CHARS)
            if isinstance(plan["recommendation"], str):
                plan["recommendation"] = _clean_text(plan["recommendation"], MAX_FIELD_CHARS)

            # Trim step summaries
            steps = plan.get("steps") or []
            if isinstance(steps, list):
                norm_steps = []
                for s in steps:
                    if isinstance(s, dict):
                        stype = str(s.get("type") or "analysis")
                        summ = _clean_text(str(s.get("summary") or ""), MAX_FIELD_CHARS)
                        norm_steps.append({"type": stype, "summary": summ})
                plan["steps"] = norm_steps

            final_answer_origin = None

            # Optional fast-path from model (accept only if looks like a true definition)
            if "final_answer" in plan and isinstance(plan["final_answer"], str):
                fa = _clean_text(plan["final_answer"].strip())
                if fa and _looks_like_definition(fa):
                    plan["final_answer"] = fa
                    final_answer_origin = "model"
                else:
                    # Reject parrot/generic FA from model
                    parrot_rejected = True
                    plan.pop("final_answer", None)

            # Deterministic synth from context if definitional and missing FA
            if is_def and not plan.get("final_answer"):
                extracted = _extract_definition_from_context(query, context)
                if extracted:
                    plan["final_answer"] = extracted
                    plan["route"] = "echo"
                    final_answer_origin = final_answer_origin or "context"
                    log_event("planner_final_answer_synthesized", {"plan_id": plan_id, "chars": len(extracted)})

            # Attach diagnostics for downstream (safe to ignore)
            plan["plan_id"] = plan.get("plan_id") or plan_id
            plan["_diag"] = {
                "coercion_used": coercion_used,
                "final_answer_origin": final_answer_origin,
                "parrot_rejected": parrot_rejected,
            }
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
                "_diag": {"coercion_used": coercion_used, "final_answer_origin": None, "parrot_rejected": False},
            }

# Export singleton (imported by agents.mcp_agent)
planner_agent = PlannerAgent()
