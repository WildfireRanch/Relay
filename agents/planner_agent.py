# File: agents/planner_agent.py
# Purpose: Relay's PlannerAgent — generates task plans from queries and context
# Handles LLM prompting, critic scoring, and structured plan shaping

import os
import json
import traceback
import uuid
from openai import AsyncOpenAI, OpenAIError

from core.logging import log_event
from agents.critic_agent import run_critics
from utils.openai_client import create_openai_client

# === Model Configuration ===
MODEL = os.getenv("PLANNER_MODEL", "gpt-4o")
openai: AsyncOpenAI = create_openai_client()

# === System Prompt: Defines planner behavior and plan schema ===
SYSTEM_PROMPT = """
You are the Planner Agent inside an AI command and control system (Relay).
Your job is to generate high-level structured plans from user input and rich context.
Plans should:
- Be actionable and decomposed into clear steps
- Reference any relevant files, sensors, functions, or context
- Suggest a route to a specialist agent (e.g. codex, docs, control)
- Avoid implementation (leave that to Codex)
- Justify the plan if useful
Return only valid JSON with keys: `objective`, `steps`, `recommendation`, `route`
""".strip()

# === PlannerAgent Class ===
class PlannerAgent:
    async def ask(self, query: str, context: str) -> dict:
        """
        Generates a structured plan from the user's query and context using OpenAI,
        runs critics on the result, and returns a JSON plan with scoring metadata.
        """
        try:
            response = await openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Query: {query}\n\nContext:\n{context}"}
                ],
                temperature=0.4,
                response_format="json"
            )

            raw = response.choices[0].message.content
            log_event("planner_response_raw", {"query": query, "output": raw[:500]})

            try:
                plan = json.loads(raw)
            except Exception:
                log_event("planner_parse_error", {"raw": raw})
                plan = {
                    "objective": "[invalid JSON returned by planner]",
                    "steps": [],
                    "recommendation": "",
                    "route": "echo",
                    "critics": []
                }

            plan["plan_id"] = str(uuid.uuid4())

            try:
                critic_results = await run_critics(plan, context)
                plan["critics"] = critic_results
                plan["passes"] = all(c.get("passes", False) for c in critic_results)

                log_event("planner_critique", {
                    "query": query,
                    "objective": plan.get("objective"),
                    "passes": plan["passes"],
                    "issues": [c for c in critic_results if not c.get("passes", True)]
                })

            except Exception as critic_error:
                log_event("planner_critic_fail", {
                    "query": query,
                    "error": str(critic_error),
                    "trace": traceback.format_exc()
                })
                plan["critics"] = [{
                    "name": "system",
                    "passes": False,
                    "issues": ["Critic system failed"]
                }]
                plan["passes"] = False

            if not plan.get("objective"):
                log_event("planner_empty_objective", {"plan": plan, "query": query})

            return plan

        except OpenAIError as e:
            log_event("planner_error", {"query": query, "error": str(e)})
            return {
                "objective": "[planner failed to generate a response]",
                "steps": [],
                "recommendation": "",
                "route": "echo",
                "critics": [],
                "passes": False,
                "plan_id": str(uuid.uuid4())
            }

        except Exception as e:
            log_event("planner_exception", {"trace": traceback.format_exc()})
            return {
                "objective": "[planner crashed unexpectedly]",
                "steps": [],
                "recommendation": "",
                "route": "echo",
                "critics": [],
                "passes": False,
                "plan_id": str(uuid.uuid4())
            }

# === Exported Instance ===
planner_agent = PlannerAgent()
