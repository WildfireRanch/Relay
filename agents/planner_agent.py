# ──────────────────────────────────────────────────────────────────────────────
# File: agents/planner_agent.py
# Purpose:
#   Robust Planner agent that turns a user query + context into a structured plan.
#   - JSON-mode with graceful fallback/coercion
#   - Retries with exponential backoff
#   - Timeouts, token ceilings, strong logging
#   - Runs critic agents and annotates result
#
# Upstream:
#   ENV: PLANNER_MODEL, PLANNER_MAX_TOKENS, PLANNER_TEMPERATURE
#   Imports: utils.openai_client (AsyncOpenAI), agents.critic_agent.run_critics
#
# Downstream:
#   agents.mcp_agent (via planner_agent.ask)
# ──────────────────────────────────────────────────────────────────────────────

import os
import json
import time
import uuid
import traceback
from typing import Any, Dict, Optional, List

from openai import AsyncOpenAI, OpenAIError

from core.logging import log_event
from agents.critic_agent import run_critics
from utils.openai_client import create_openai_client

# === Model & generation config ===
MODEL = os.getenv("PLANNER_MODEL", "gpt-4o")  # set to a JSON-capable model in prod
MAX_OUT_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "800"))
TEMPERATURE = float(os.getenv("PLANNER_TEMPERATURE", "0.2"))
REQUEST_TIMEOUT_S = int(os.getenv("PLANNER_TIMEOUT_S", "45"))

openai: AsyncOpenAI = create_openai_client()

# === System Prompt: schema and behavior ===
SYSTEM_PROMPT = """
You are the Planner inside the Relay system. Produce a concise JSON plan only.

Rules:
- Return strictly valid JSON (no markdown, no commentary).
- Keys: "objective": string, "steps": [{"type":"analysis|action|docs|control","summary":string}], "recommendation": string, "route": "echo|codex|docs|control"
- Keep steps short and executable. Do not implement code.
""".strip()


def _schema_ok(d: Dict[str, Any]) -> bool:
    return (
        isinstance(d, dict)
        and "objective" in d
        and "steps" in d
        and isinstance(d["steps"], list)
        and "route" in d
    )


def _coerce_plan(raw_text: str) -> Optional[Dict[str, Any]]:
    """Try to parse JSON from a messy response."""
    try:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw_text[start : end + 1])
    except Exception:
        pass
    return None


def _prompt(query: str, context: str) -> List[Dict[str, str]]:
    """Build ChatML messages; keep context reasonable (pre-truncated upstream)."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Query: {query}\n\nContext:\n{context}"},
    ]


class PlannerAgent:
    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call the LLM with retries and JSON mode; return text content."""
        last_err = None
        for attempt in range(3):
            try:
                resp = await openai.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_OUT_TOKENS,
                    # Use JSON mode if the model supports it. If it doesn't, the API
                    # returns a 400 and we fall back to coercion on the next attempt.
                    response_format={"type": "json_object"},
                    timeout=REQUEST_TIMEOUT_S,
                )
                content = getattr(resp.choices[0].message, "content", "") if resp and resp.choices else ""
                if not content:
                    raise OpenAIError("Empty content from model")  # triggers retry
                return content
            except OpenAIError as e:
                last_err = e
                wait = 2 ** attempt
                log_event("planner_llm_retry", {"attempt": attempt + 1, "error": str(e), "wait_s": wait})
                time.sleep(wait)
            except Exception as e:
                last_err = e
                wait = 2 ** attempt
                log_event("planner_llm_retry_unknown", {"attempt": attempt + 1, "error": str(e), "wait_s": wait})
                time.sleep(wait)

        # After retries, raise a descriptive error
        raise RuntimeError(f"Planner LLM call failed after retries: {last_err}")

    async def ask(self, query: str, context: str) -> dict:
        """
        Generate a structured plan for (query, context).
        Returns a dict with keys objective/steps/recommendation/route/critics/passes/plan_id.
        Never raises; returns a safe failure object on error.
        """
        plan_id = str(uuid.uuid4())
        try:
            messages = _prompt(query, context)
            raw_text = await self._call_llm(messages)
            log_event("planner_response_raw", {"plan_id": plan_id, "sample": raw_text[:800]})

            # Primary parse
            try:
                plan = json.loads(raw_text)
            except Exception:
                plan = _coerce_plan(raw_text)

            if not plan:
                log_event("planner_parse_error", {
                    "plan_id": plan_id,
                    "query": query,
                    "raw_head": raw_text[:1500],
                    "trace": traceback.format_exc(),
                })
                plan = {
                    "objective": "[invalid JSON returned by planner]",
                    "steps": [],
                    "recommendation": "",
                    "route": "echo",
                }

            # Minimal schema enforcement
            plan.setdefault("objective", "")
            plan.setdefault("steps", [])
            plan.setdefault("recommendation", "")
            plan.setdefault("route", "echo")

            # Truncate overly verbose step summaries
            for s in plan.get("steps", []):
                if isinstance(s, dict) and isinstance(s.get("summary"), str) and len(s["summary"]) > 500:
                    s["summary"] = s["summary"][:500] + "…"

            plan["plan_id"] = plan_id

            # === Run critics ===
            try:
                critic_results = await run_critics(plan, context)
                plan["critics"] = critic_results
                plan["passes"] = all(c.get("passes", False) for c in critic_results)
                log_event("planner_critique", {
                    "plan_id": plan_id,
                    "objective": plan.get("objective"),
                    "passes": plan["passes"],
                    "issues": [c for c in critic_results if not c.get("passes", True)],
                })
            except Exception as critic_error:
                log_event("planner_critic_fail", {
                    "plan_id": plan_id,
                    "error": str(critic_error),
                    "trace": traceback.format_exc(),
                })
                plan["critics"] = [{"name": "system", "passes": False, "issues": ["Critic system failed"]}]
                plan["passes"] = False

            if not plan.get("objective"):
                log_event("planner_empty_objective", {"plan_id": plan_id, "plan": plan, "query": query})

            return plan

        except Exception as e:
            # Final safety: never bubble an exception beyond Ask route.
            log_event("planner_exception", {
                "plan_id": plan_id,
                "query": query,
                "error": str(e),
                "trace": traceback.format_exc(),
                "model": MODEL,
                "temp": TEMPERATURE,
                "max_tokens": MAX_OUT_TOKENS,
            })
            return {
                "objective": "[planner failed to generate a response]",
                "steps": [],
                "recommendation": "",
                "route": "echo",
                "critics": [],
                "passes": False,
                "plan_id": plan_id,
            }


# === Exported instance ===
planner_agent = PlannerAgent()
