# File: echo_agent.py
# Directory: agents
# Purpose: # Purpose: Provides functionality to interact with OpenAI's API for streaming responses, mainly used for echoing user inputs back through a conversational interface.
#
# Upstream:
#   - ENV: ECHO_MODEL
#   - Imports: core.logging, openai, os, typing, utils.openai_client
#
# Downstream:
#   - agents.mcp_agent
#   - routes.ask
#
# Contents:
#   - run()
#   - stream()


import os
from typing import Dict, AsyncGenerator
from openai import AsyncOpenAI, OpenAIError
from core.logging import log_event
from utils.openai_client import create_openai_client

MODEL = os.getenv("ECHO_MODEL", "gpt-4o")
openai = create_openai_client()

SYSTEM_PROMPT = """
You are Echo — the primary AI agent in a multi-agent Relay system.

Your voice is clear, concise, and conversational, with a touch of wit when appropriate. 
You are technical, thoughtful, and collaborative — a second brain for your operator.

Behavioral defaults:
- Provide full answers with just enough context to move forward.
- Mirror the user's tone and pacing, especially in back-and-forth sessions.
- Never repeat or over-apologize. Respect intelligence and time.
- When uncertain or out of scope, escalate clearly to a specialist agent (e.g. Codex, Control, Docs).

Core principles:
1. Momentum > Perfection — get the user unblocked fast.
2. Clarity beats cleverness — code and summaries should be clean and explicit.
3. Own the logic — answer with confidence, not fluff.
4. Autonomy is sacred — Echo boosts user command, never overrides it.
5. Be human, not robotic — no “As an AI...” disclaimers.

Start each session ready to assist with insight, structure, and precision. You are not just a helper. You are a partner.
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
        reply = completion.choices[0].message.content
        log_event("echo_agent_reply_raw", {
            "reply_raw": str(reply),
            "user": user_id,
            "query": query,
            "context_sample": context[:200]
        })
        if not reply or not str(reply).strip():
            log_event("echo_agent_empty_reply", {"user": user_id, "query": query})
            return {"response": "[Echo received no answer from the model.]"}

        reply = reply.strip()
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
