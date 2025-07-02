# File: agents/echo_agent.py
# Purpose: Fallback LLM responder when no specialized agent is routed
# Role: General Q&A, summarization, explanation, or chat-like fallback

import os
from typing import Dict, AsyncGenerator
from openai import AsyncOpenAI, OpenAIError
from core.logging import log_event
from utils.openai_client import create_openai_client

MODEL = os.getenv("ECHO_MODEL", "gpt-4o")
openai = create_openai_client()

SYSTEM_PROMPT = """
You are Echo, the default AI agent in a multi-agent relay system.
Answer clearly, concisely, and conversationally.
If asked to perform a task better suited for a specialist agent (e.g. Codex, Control), acknowledge and suggest escalation.
""".strip()

async def run(
    query: str, 
    context: str = "", 
    user_id: str = "anonymous"
) -> Dict[str, str]:
    """
    General fallback responder. Used when no specialized agent is mapped to the query.
    Returns:
        dict: {"response": reply} or {"error": "..."}
    """
    try:
        completion = await openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{query}\n\nContext:\n{context}"}
            ],
            temperature=0.7,
        )
        reply = completion.choices[0].message.content.strip()
        log_event("echo_agent_reply", {
            "user": user_id, 
            "reply": reply[:500],  # log only first 500 chars for readability
            "query": query,
            "context_sample": context[:200]
        })
        return {"response": reply}

    except OpenAIError as e:
        log_event("echo_agent_error", {
            "error": str(e), 
            "user_id": user_id,
            "query": query
        })
        return {"error": "Echo failed to respond."}


async def stream(
    query: str,
    context: str = "",
    user_id: str = "anonymous"
) -> AsyncGenerator[str, None]:
    """
    Streams the Echo agent response chunk by chunk.
    """
    try:
        response_stream = await openai.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{query}\n\nContext:\n{context}"}
            ],
            temperature=0.7,
            stream=True,
        )
        async for chunk in response_stream:
            delta = getattr(chunk.choices[0].delta, "content", None)
            if delta:
                yield delta
    except OpenAIError as e:
        log_event("echo_agent_stream_error", {
            "error": str(e),
            "user_id": user_id,
            "query": query
        })
        yield f"[Error] Echo stream failed: {str(e)}"

# Export for import in routes/ask.py or MCP
stream = stream
