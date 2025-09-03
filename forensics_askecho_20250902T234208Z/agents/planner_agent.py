# File: agents/planner_agent.py
# Purpose: Token-efficient, high-context planner that returns a strict JSON "plan"
#          and guarantees a synthesized `final_answer` for definitional prompts.
#          Maintains existing contract/telemetry and remains upstream/downstream compatible.
#
# Inputs:
#   - ENV (required): OPENAI_API_KEY
#   - ENV (optional):
#       PLANNER_MODEL           (default "gpt-4o")
#       PLANNER_CTX_TOKENS      (default "128000")  # approximate model context window
#       PLANNER_MAX_TOKENS      (default "800")     # max output tokens
#       PLANNER_TEMPERATURE     (default "0.2")
#       PLANNER_TIMEOUT_S       (default "45")
#       PLANNER_MAX_RETRIES     (default "3")
#       OPENAI_MAX_RETRIES      (fallback for PLANNER_MAX_RETRIES if set)
#
# Contract (unchanged):
#   Returns dict with:
#     { "objective": str, "steps": [{type, summary}], "recommendation": str,
#       "route": "echo"|"codex"|"docs"|"control",
#       "plan_id": str, ["final_answer": str]?, "_diag": {...} }
#
# Notes:
#   - Strict JSON (model forced to json_object).
#   - Robust, non-parrot final_answer policy:
#       * Prefer model-provided FA if it looks definitional (not a restatement)
#       * Else synthesize deterministically from packed context
#   - Token budgeter + context packer avoid waste and maximize useful signal.
#   - Keeps ALLOWED_ROUTES and uses log_event at key points.

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from openai import APIError as OpenAIError
from core.logging import log_event
from utils.openai_client import create_openai_client

# ── Config ──────────────────────────────────────────────────────────────────

MODEL = os.getenv("PLANNER_MODEL", "gpt-4o")
CTX_TOKENS = int(os.getenv("PLANNER_CTX_TOKENS", "128000"))  # approximate window
MAX_OUT_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "800"))
TEMPERATURE = float(os.getenv("PLANNER_TEMPERATURE", "0.2"))
REQUEST_TIMEOUT_S = int(os.getenv("PLANNER_TIMEOUT_S", "45"))
MAX_RETRIES = int(os.getenv("PLANNER_MAX_RETRIES", os.getenv("OPENAI_MAX_RETRIES", "3")))

# Defensive caps
MAX_FIELD_CHARS = 800
MAX_FINAL_ANSWER_CHARS = 600
SAFETY_TOKENS = 800  # headroom for JSON/object framing etc.

ALLOWED_ROUTES = {"echo", "codex", "docs", "control"}

_openai = create_openai_client()

# ── Prompt (explicit FA + anti-parrot) ──────────────────────────────────────

SYSTEM_PROMPT = (
    "You are the Planner inside the Relay system. Produce a concise JSON object only.\n\n"
    "Rules:\n"
    "- Return strictly valid JSON (no markdown, no commentary).\n"
    "- Keys:\n"
    '  \"objective\": str,\n'
    '  \"steps\": [{\"type\": \"analysis|action|docs|control\", \"summary\": str}],\n'
    '  \"recommendation\": str,\n'
    '  \"route\": \"echo\" | \"codex\" | \"docs\" | \"control\",\n'
    '  \"final_answer\"?: str.\n'
    "- If the user question is a DEFINITION-STYLE prompt (starts with what/who/define/describe/explain) "
    "AND the CONTEXT contains an actual definition, then:\n"
    "  • Populate \"final_answer\" with a concise 2–4 sentence factual answer.\n"
    "  • Do NOT restate the question; avoid \"What is...\" phrasing.\n"
    "  • Set route to \"echo\".\n"
    "- Keep plans short and executable; do not write code."
)

# ── Regex + heuristics ──────────────────────────────────────────────────────

_FENCE_PAT = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_DEFN_PREFIXES = ("what is", "who is", "define", "describe", "explain")
_PARROT_PAT = re.compile(r"^\s*(what\s+is|who\s+is|define|describe|explain)\b", re.I)
_HEADING_PAT = re.compile(r"^\s*#{1,6}\s*")
_STOPWORDS = {
    "what", "who", "is", "the", "a", "an", "define", "describe", "explain",
    "of", "in", "for", "to", "on", "and", "or", "with", "about"
}
_BAD_SUMMARY_MARKERS = (
    "project summary not available",
    "global project context not available",
    "semantic retrieval unavailable",
    "[semantic retrieval unavailable]",
)

def _clean_text(t: str, cap: int = MAX_FINAL_ANSWER_CHARS) -> str:
    if not t:
        return ""
    t = _FENCE_PAT.sub("", t).strip()
    t = " ".join(t.split())
    if len(t) > cap:
        t = t[:cap].rstrip() + "…"
    return t

def _is_definitional(q: str) -> bool:
    ql = (q or "").strip().lower().rstrip(" ?!.:")
    return any(ql.startswith(p) for p in _DEFN_PREFIXES)

def _looks_like_definition(s: str) -> bool:
    """
    Accept common definition phrasings:
      - 'X is a/an ...'
      - 'X — a/an ...' (dash)
      - 'X: a/an ...' (colon)
      - 'X, a/an ...' (apposition)
    Reject restatements like 'What is ...'
    """
    ls = (s or "").strip().lower()
    if not ls or _PARROT_PAT.match(ls):
        return False
    if " is a " in ls or " is an " in ls:
        return True
    if re.search(r"\b[a-z0-9][\s\-–—]*[:\-–—]\s*(a|an)\s+\b", ls):
        return True
    if re.search(r"\b,\s*(a|an)\s+\b", ls):
        return True
    return False

def _filter_context_lines(context: str) -> List[str]:
    out: List[str] = []
    for ln in (context or "").splitlines():
        ls = ln.strip()
        lsl = ls.lower()
        if not ls or _HEADING_PAT.match(ls) or any(m in lsl for m in _BAD_SUMMARY_MARKERS):
            continue
        out.append(ls)
    return out

def _approx_tokens(s: str) -> int:
    """Cheap token estimate to budget context (avoid external deps)."""
    if not s:
        return 0
    # words * 1.3 is a decent heuristic for GPT-* tokenization in English prose
    return int(len(s.split()) * 1.3)

def _key_from_query(query: str) -> str:
    toks = re.sub(r"[^a-zA-Z0-9\s\-_/]", " ", (query or "")).lower().split()
    content = [t for t in toks if t not in _STOPWORDS]
    return " ".join(content[-3:]) if content else ""

def _score_para(para: str, q_tokens: List[str]) -> float:
    """Simple relevance: coverage + density."""
    pl = para.lower()
    if not pl:
        return 0.0
    hits = sum(1 for t in q_tokens if t and t in pl)
    if hits == 0:
        return 0.0
    length = max(len(para.split()), 1)
    return hits + (hits / length)

def _pack_context(query: str, raw_context: str, budget_tokens: int) -> Tuple[str, Dict[str, Any]]:
    """
    Deduplicate, rank, and pack paragraphs under a token budget.
    Returns (packed, diag)
    """
    lines = _filter_context_lines(raw_context)
    if not lines:
        return "", {"kept_paras": 0, "total_paras": 0, "est_tokens": 0}

    text = "\n".join(lines)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # Deduplicate paragraphs conservatively
    seen = set()
    unique: List[str] = []
    for p in paras:
        key = p[:256].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    q_key = _key_from_query(query)
    q_tokens = [t for t in q_key.split() if t]

    scored = sorted(
        ((p, _score_para(p, q_tokens)) for p in unique),
        key=lambda x: x[1],
        reverse=True,
    )

    packed_parts: List[str] = []
    used_tokens = 0
    kept = 0

    # Always try to include the single best definitional-looking paragraph if present
    best_def: Optional[str] = None
    for p, _ in scored[:20]:  # small lookahead window
        if _looks_like_definition(p):
            best_def = p
            break

    def try_add(paragraph: str) -> bool:
        nonlocal used_tokens, kept
        t = _approx_tokens(paragraph) + 1  # +1 for newline
        if used_tokens + t > budget_tokens:
            return False
        packed_parts.append(paragraph)
        used_tokens += t
        kept += 1
        return True

    if best_def:
        try_add(best_def)

    for p, _ in scored:
        if best_def and p == best_def:
            continue
        if not try_add(p):
            break

    packed = "\n\n".join(packed_parts)
    return packed, {
        "kept_paras": kept,
        "total_paras": len(unique),
        "est_tokens": used_tokens,
        "q_key": q_key,
    }

def _extract_definition_from_context(query: str, context: str, max_chars: int = MAX_FINAL_ANSWER_CHARS) -> Optional[str]:
    if not context:
        return None
    clean_ctx = "\n".join(_filter_context_lines(context))
    paras = [p.strip() for p in re.split(r"\n\s*\n", clean_ctx) if p.strip()]
    if not paras:
        paras = [clean_ctx.strip()] if clean_ctx.strip() else []

    key = _key_from_query(query)
    cand: Optional[str] = None
    if key:
        for p in paras:
            if key in p.lower():
                cand = p
                break
    if not cand:
        for p in paras:
            if _looks_like_definition(p):
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
    out = _clean_text(out, max_chars)
    if not _looks_like_definition(out):
        return None
    return out or None

# ── Planner ─────────────────────────────────────────────────────────────────

class PlannerAgent:
    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """
        Invoke OpenAI with JSON mode and logical retries.
        Backoff: 1s, 2s, 4s, capped.
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
        raise OpenAIError(f"Planner LLM failed after {MAX_RETRIES} attempts: {last_err}")

    async def ask(self, query: str, context: str) -> Dict[str, Any]:
        """
        Build a plan for the given query using the provided (possibly large) context.
        Token-budgeted packing ensures efficient, high-signal prompts.

        Returns at least:
          { "objective": str, "steps": [], "recommendation": str, "route": "echo|codex|docs|control",
            "plan_id": str, ["final_answer": str]? , "_diag": {...} }
        """
        plan_id = str(uuid.uuid4())
        is_def = _is_definitional(query or "")

        # Compute prompt token budget
        # Rough overhead for system + user framing
        overhead_tokens = _approx_tokens(SYSTEM_PROMPT) + _approx_tokens(query) + 200
        # Budget for context portion
        ctx_budget = max(0, CTX_TOKENS - MAX_OUT_TOKENS - SAFETY_TOKENS - overhead_tokens)

        packed_context, pack_diag = _pack_context(query, context or "", ctx_budget)
        log_event("planner_context_packed", {"plan_id": plan_id, **pack_diag, "ctx_budget": ctx_budget})

        def_hint = (
            "\n\nINSTRUCTION: If this is a definition-style question and the CONTEXT contains a definition, "
            'populate "final_answer" with a concise 2–4 sentence factual answer (no restatement) and set route to "echo".'
            if is_def else ""
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"QUESTION:\n{query}\n\nCONTEXT:\n{packed_context or '[none]'}{def_hint}"},
        ]

        coercion_used = False
        parrot_rejected = False
        final_answer_origin: Optional[str] = None

        try:
            raw = await self._call_llm(messages)
            log_event("planner_response_raw", {"plan_id": plan_id, "sample": raw[:800]})

            # Parse JSON, then coerce if needed
            try:
                plan: Dict[str, Any] = json.loads(raw)
            except Exception:
                plan = self._coerce_json_object(raw) or {}
                coercion_used = True

            if not isinstance(plan, dict):
                log_event("planner_parse_error", {"plan_id": plan_id, "head": raw[:1200]})
                plan = {"objective": "[invalid JSON from model]", "steps": [], "recommendation": "", "route": "echo"}

            # ---- Normalize schema
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

            # ---- Final answer policy
            if "final_answer" in plan and isinstance(plan["final_answer"], str):
                fa = _clean_text(plan["final_answer"].strip())
                if fa and _looks_like_definition(fa):
                    plan["final_answer"] = fa
                    final_answer_origin = "model"
                else:
                    parrot_rejected = True
                    plan.pop("final_answer", None)

            # Deterministic synth from packed context if definitional and missing FA
            if is_def and not plan.get("final_answer"):
                extracted = _extract_definition_from_context(query, packed_context)
                if extracted:
                    plan["final_answer"] = extracted
                    plan["route"] = "echo"
                    final_answer_origin = final_answer_origin or "context"
                    log_event("planner_final_answer_synthesized", {"plan_id": plan_id, "chars": len(extracted)})

            # Attach diagnostics
            plan["plan_id"] = plan.get("plan_id") or plan_id
            plan["_diag"] = {
                "coercion_used": coercion_used,
                "final_answer_origin": final_answer_origin,
                "parrot_rejected": parrot_rejected,
                "ctx": {
                    "budget_tokens": ctx_budget,
                    "est_used_tokens": pack_diag.get("est_tokens", 0),
                    "kept_paras": pack_diag.get("kept_paras", 0),
                    "total_paras": pack_diag.get("total_paras", 0),
                    "q_key": pack_diag.get("q_key"),
                },
            }

            # Emit a compact reply head for telemetry/observability (safe to ignore downstream)
            if plan.get("final_answer"):
                reply_head = plan["final_answer"]
                log_event("planner_reply_head", {"plan_id": plan_id, "reply_head": reply_head[:300]})

            return plan

        except Exception as e:
            log_event("planner_failed", {"plan_id": plan_id, "error": str(e)})
            return {
                "objective": "[planner failed]",
                "steps": [],
                "recommendation": "",
                "route": "echo",
                "plan_id": plan_id,
                "_diag": {
                    "coercion_used": coercion_used,
                    "final_answer_origin": None,
                    "parrot_rejected": False,
                    "ctx": {"budget_tokens": 0, "est_used_tokens": 0, "kept_paras": 0, "total_paras": 0},
                },
            }

    @staticmethod
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


# Export singleton (imported by agents.mcp_agent)
planner_agent = PlannerAgent()
