# File: agents/planner_agent.py
# Purpose: Generate intelligent task plans from user queries and injected context — safely and with consistent output

import os
import json
import traceback
from openai import AsyncOpenAI, OpenAIError
from core.logging import log_event
from agents.critic_agent import run_critics
from utils.openai_client import create_openai_client

# === Model Configuration ===
MODEL = os.getenv("PLANNER_MODEL", "gpt-4o")
openai = create_openai_client()

# === System Prompt: Define role and structure for planner output ===
SYSTEM_PROMPT = """
You are the Planner Agent inside an AI command and control system (Relay).
Your job is to generate high-level structured plans from user input and rich context.
Plans should:
- Be actionable and decomposed into clear steps
- Reference any relevant files, sensors, functions, or context
- Avoid implementation (leave that to Codex)
- Provide justifications if appropriate
Return only valid JSON with keys: `objective`, `steps`, `recommendation`
""".strip()

# === Planner Agent Entrypoint ===
async def ask(query: str, context: str) -> dict:
    """
    Main planner interface. Accepts user query and full context string,
    returns structured plan as dictionary. Runs all critics post-generation.
    """
    try:
        # === Step 1: Query LLM with system + user messages ===
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

        # === Step 2: Safely parse LLM JSON output ===
        try:
            plan = json.loads(raw)
        except Exception:
            log_event("planner_parse_error", {"raw": raw})
            plan = {
                "objective": "[invalid JSON returned by planner]",
                "steps": [],
                "recommendation": "",
                "critics": []
            }

        # === Step 3: Run Critics ===
        try:
            critic_results = await run_critics(plan, context)
            plan["critics"] = critic_results
            log_event("planner_critique", {
                "query": query,
                "objective": plan.get("objective"),
                "passes": all(c.get("passes", False) for c in critic_results),
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

        # === Step 4: Final safety check ===
        if not plan.get("objective"):
            log_event("planner_empty_objective", {"plan": plan, "query": query})

        return plan

    except OpenAIError as e:
        log_event("planner_error", {"query": query, "error": str(e)})
        return {
            "objective": "[planner failed to generate a response]",
            "steps": [],
            "recommendation": "",
            "critics": []
        }

    except Exception as e:
        log_event("planner_exception", {"trace": traceback.format_exc()})
        return {
            "objective": "[planner crashed unexpectedly]",
            "steps": [],
            "recommendation": "",
            "critics": []
        }
