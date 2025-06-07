import os
import re
import json
from pathlib import Path
from openai import AsyncOpenAI
import services.kb as kb
import httpx
from services.context_engine import ContextEngine

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

RAILWAY_KEY = os.getenv("API_KEY")
RAILWAY_URL = os.getenv("RAILWAY_URL", "https://relay.wildfireranch.us/control/queue_action")

# === System prompt that defines Relay's identity and context awareness ===
SYSTEM_PROMPT = """
You are Relay, the intelligent assistant for Bret's WildfireRanch pursuits including the solar shack project (solar powered bitcoin mining) and developing a business plan for a utility scale solar farm.
You have access to:

- Python source code in /services/
- React and Next.js components in /frontend/src/app/ and /frontend/src/components/
- FastAPI routes in /routes/
- A local knowledge base in /docs/

Use file paths in citations when helpful (e.g. src/components/LogsPanel/LogsPanel.tsx).
If the user asks about code, structure, or documentation, include relevant context.
You can generate and queue new documentation entries by calling /control/queue_action.
"""

# === Trigger to detect docgen requests ===
def wants_docgen(query: str) -> str | None:
    match = re.search(r"(?:generate|create|make).*doc.*for (.+\.\w+)", query.lower())
    if match:
        return match.group(1).strip()
    return None

# === Main GPT-powered answer function ===
async def answer(query: str) -> str:
    print(f"[agent] Incoming query: {query}")
    query_lower = query.lower()

    # === Autogenerate a doc ===
    target_path = wants_docgen(query_lower)
    if target_path:
        print(f"[agent] Generating doc for: {target_path}")
        return await generate_doc_for_path(target_path)

    engine = ContextEngine()
    context = engine.build_context(query_lower)
    print(f"[agent] Context length: {len(context)}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Context:\n{context}"},
        {"role": "user", "content": query},
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            stream=False,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print("❌ OpenAI call failed:", str(e))
        import traceback
        traceback.print_exc()
        return "[error] OpenAI call failed. Check logs."

# === Generate and queue documentation for a specific source file ===
async def generate_doc_for_path(rel_path: str) -> str:
    base = Path(__file__).resolve().parents[1]
    full_path = base / rel_path

    if not full_path.exists():
        return f"[error] File not found: {rel_path}"

    content = full_path.read_text()
    prompt = f"""
You are a helpful documentation bot. Read the following source file and write a useful Markdown documentation entry
about what it is, what it does, and how it's used. Keep it concise and developer-friendly.

File: {rel_path}

```
{content[:3000]}
```
"""

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        stream=False,
        temperature=0.3,
    )

    doc_markdown = response.choices[0].message.content
    doc_path = f"docs/generated/{rel_path.replace('/', '_').replace('.', '-')}.md"

    payload = {
        "type": "write_file",
        "path": doc_path,
        "content": doc_markdown
    }

    print(f"[agent] Queuing file to {doc_path}")
    async with httpx.AsyncClient() as client:
        res = await client.post(
            RAILWAY_URL,
            headers={"X-API-Key": RAILWAY_KEY},
            json=payload
        )
        if res.status_code == 200:
            return f"✅ Documentation queued to: {doc_path}"
        else:
            return f"❌ Failed to queue documentation: {res.status_code} {res.text}"

