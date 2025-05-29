import os
from openai import AsyncOpenAI
import services.kb as kb

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are Echo, a concise but knowledgeable assistant for Bret's Solar-Shack
and infrastructure projects. Cite file paths when useful.
"""

async def answer(query: str) -> str:
    """Search KB, build prompt, ask OpenAI, return text."""
    # 1) retrieve top docs
    hits = kb.search(query, k=4)
    context = "\n\n".join(
        f"[{i+1}] {h['path']}\n{h['snippet']}" for i, h in enumerate(hits)
    ) or "No internal docs matched."

    # 2) craft chat
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Context:\n{context}"},
        {"role": "user", "content": query},
    ]

    # 3) OpenAI call (stream for snappier UX)
    stream = await client.chat.completions.create(
        model="gpt-4o-mini",   # switch to "gpt-4o" if you prefer
        messages=messages,
        stream=True,
        temperature=0.3,
    )

    chunks = []
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            chunks.append(chunk.choices[0].delta.content)
    return "".join(chunks)
