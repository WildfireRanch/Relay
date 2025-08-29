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

# System prompt instructs the model to:
#  - Return STRICT JSON (no markdown)
#  - Include a definition fast-path via `final_answer` when applicable
SYSTEM_PROMPT = (
    "You are the Planner inside the Relay system. Produce a concise JSON object only.\n\n"
    "Rules:\n"
    '- Return strictly valid JSON (no markdown, no commentary).\n'
    '- Keys:\n'
    '  "objective": str,\n'
    '  "steps": [{"type": "analysis|action|docs|control", "summary": str}],\n'
    '  "recommendation": str,\n'
    '  "route": "echo" | "codex" | "docs" | "control".\n'
    "- If the user question is a direct definition/what/describe and the provided CONTEXT contains "
    'enough information, set "final_answer" to a concise 2–4 sentence answer and choose route "echo".\n'
    "- Keep plans short and executable; do not write code."
)


def _coerce_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort extraction of the first JSON object from a text blob.
    Returns dict or None.
    """
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
    except Exception:
        pass
    return None


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
                log_event(
                    "planner_llm_retry",
                    {"attempt": attempt, "wait_s": wait, "error": str(e)},
                )
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
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"QUESTION:\n{query}\n\nCONTEXT:\n{context or '[none]'}"},
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
                plan = {
                    "objective": "[invalid JSON from model]",
                    "steps": [],
                    "recommendation": "",
                    "route": "echo",
                }

            # Minimal schema normalization
            plan.setdefault("objective", "")
            plan.setdefault("steps", [])
            plan.setdefault("recommendation", "")
            plan.setdefault("route", "echo")

            # Optional fast-path (when present, Echo will surface it as the direct answer)
            if "final_answer" in plan and isinstance(plan["final_answer"], str):
                plan["final_answer"] = plan["final_answer"].strip()

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
