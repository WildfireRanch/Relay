# ──────────────────────────────────────────────────────────────────────────────
# File: agents/planner_agent.py
# Purpose: Generate intelligent task plans from user queries and injected context
# ──────────────────────────────────────────────────────────────────────────────

import os
import traceback
from openai import AsyncOpenAI, OpenAIError
from core.logging import log_event
from agents.critic_agent import run_all as run_critics

# === Model Configuration ===
MODEL = os.getenv("PLANNER_MODEL", "gpt-4o")
openai = AsyncOpenAI()

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
        log_event("planner_response", {"query": query, "output": raw[:500]})
        plan = eval(raw)  # Unsafe in prod, assumes clean JSON

        # === Step 1: Run Planner Critics ===
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
            plan["critics"] = [{"name": "system", "passes": False, "issues": ["Critic system failed"]}]

        return plan

    except OpenAIError as e:
        log_event("planner_error", {"query": query, "error": str(e)})
        return {"error": "Planner failed to generate a response."}

    except Exception as e:
        log_event("planner_exception", {"trace": traceback.format_exc()})
        return {"error": "Unexpected error in planner agent."}
