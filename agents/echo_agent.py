# File: agents/echo_agent.py
# Purpose: Fallback LLM responder when no specialized agent is routed
# Role: General Q&A, summarization, explanation, or chat-like fallback

import os
from openai import AsyncOpenAI, OpenAIError
from core.logging import log_event

MODEL = os.getenv("ECHO_MODEL", "gpt-4o")
openai = AsyncOpenAI()

SYSTEM_PROMPT = """
You are Echo, the default AI agent in a multi-agent relay system.
Answer clearly, concisely, and conversationally.
If asked to perform a task better suited for a specialist agent (e.g. Codex, Control), acknowledge and suggest escalation.
""".strip()


async def run(query: str, context: str = "", user_id: str = "anonymous") -> dict:
    """
    General fallback responder. Used when no specialized agent is mapped to the query.
    Returns a direct conversational response.
    """
    try:
        completion = await openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{query}\n\nContext:\n{context}"}
            ],
            temperature=0.7
        )

        reply = completion.choices[0].message.content.strip()
        log_event("echo_agent_reply", {"user": user_id, "reply": reply[:500]})
        return {"response": reply}

    except OpenAIError as e:
        log_event("echo_agent_error", {"error": str(e), "user_id": user_id})
        return {"error": "Echo failed to respond."}
