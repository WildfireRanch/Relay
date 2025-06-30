# File: agents/docs_agent.py
# Purpose: Analyze document content and produce structured summaries or plans
# Includes critic review (structure, logic, safety) of generated insights

import os
import traceback
from openai import AsyncOpenAI, OpenAIError
from agents.critic_agent import run_critics
from core.logging import log_event

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === System Prompt ===
SYSTEM_PROMPT = """
You are an expert technical analyst. Given a longform document and user query,
extract a concise plan, summary, or insight. Always return valid JSON like:

{
  "objective": "",
  "steps": ["..."],
  "recommendation": ""
}

Avoid repeating the full doc. Focus on useful, structured information.
""".strip()


async def analyze(query: str, context: str, user_id: str = "anonymous") -> dict:
    """
    Analyzes document content in light of user query. Returns structured summary + critic results.
    """
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Query: {query}\n\nDocument:\n{context}"}
            ],
            temperature=0.4,
            response_format="json"
        )

        raw = completion.choices[0].message.content.strip()
        log_event("docs_agent_raw", {"query": query, "output": raw[:500]})
        summary = eval(raw)  # Assumes valid JSON

        critics = await run_critics(summary, context)
        summary["critics"] = critics

        log_event("docs_agent_critique", {
            "user": user_id,
            "objective": summary.get("objective"),
            "passes": all(c.get("passes", False) for c in critics),
            "issues": [c for c in critics if not c.get("passes", True)]
        })

        return summary

    except OpenAIError as e:
        log_event("docs_agent_error", {"error": str(e), "user_id": user_id})
        return {"error": "OpenAI failed to respond."}

    except Exception as e:
        log_event("docs_agent_exception", {"trace": traceback.format_exc()})
        return {"error": "Unexpected error in docs agent."}
