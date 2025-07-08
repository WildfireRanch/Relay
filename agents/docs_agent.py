# File: docs_agent.py
# Directory: agents
# Purpose: # Purpose: Manages the documentation analysis process using AI models to assess and improve content quality.
#
# Upstream:
#   - ENV: —
#   - Imports: agents.critic_agent, core.logging, json, openai, os, traceback, utils.openai_client
#
# Downstream:
#   - agents.mcp_agent
#
# Contents:
#   - DocsAgent()
#   - analyze()









import os
import traceback
from openai import AsyncOpenAI, OpenAIError
from agents.critic_agent import run_critics
from core.logging import log_event
from utils.openai_client import create_openai_client

client = create_openai_client()

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


class DocsAgent:
    async def analyze(self, query: str, context: str, user_id: str = "anonymous") -> dict:
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
            summary = json.loads(raw)
            
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

import json
# Exported instance
docs_agent = DocsAgent()
analyze = docs_agent.analyze

