# File: services/summarize_memory.py
# Directory: services/
# Purpose: Use OpenAI to generate concise summary of a user-agent memory exchange

import os
from openai import AsyncOpenAI
from utils.openai_client import create_openai_client

client = create_openai_client()

async def summarize_memory_entry(question: str, response: str, context: str = "") -> str:
    prompt = f"""
You are a concise summarizer of agent interactions.

Summarize this user query and response in 1–2 sentences for memory recall:

Q: {question}

Agent response: {response}

Context (if needed):
{context[:500]}

Summary:
"""
    result = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return result.choices[0].message.content.strip()
