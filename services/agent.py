# File: agent.py
# Directory: services/agent.py

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
import services.kb as kb
import httpx
from services.context_engine import ContextEngine

# === Initialize OpenAI client ===
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === Railway control endpoint for queueing actions/docs ===
RAILWAY_KEY = os.getenv("API_KEY")
RAILWAY_URL = os.getenv("RAILWAY_URL", "https://relay.wildfireranch.us/control/queue_action")

# === System prompt to define Relay's identity and context awareness ===
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

# === Helper: detect requests to autogenerate docs ===
def wants_docgen(query: str) -> Optional[str]:
    match = re.search(r"(?:generate|create|make).*doc.*for ([\w/\\.]+\.\w+)", query.lower())
    return match.group(1).strip() if match else None

# === In-memory store for multi-turn history ===
conversation_history: Dict[str, List[Dict[str, Any]]] = {}

# === Tool dispatchers ===
async def search_docs(query: str, user_id: str) -> Dict[str, Any]:
    """
    Search the local /docs directory via the KB service.
    Returns matching paths and snippets.
    """
    hits = kb.search(query, user_id=user_id, k=5)
    return {"matches": hits}

async def run_code_review(path: str) -> Dict[str, Any]:
    """
    Basic static analysis stub for a source file.
    Returns a placeholder issue list with file summary.
    """
    base = Path(__file__).resolve().parents[1]
    target = base / path
    if not target.exists() or not target.is_file():
        return {"issues": [{"path": path, "error": "File not found"}]}  
    content = target.read_text()
    # Stub: return file length as a summary issue
    return {"issues": [{"path": path, "summary": f"File loaded, {len(content)} characters"}]}  

# === Reflection & plan generation ===
async def reflect_and_plan(user_id: str, query: str) -> Dict[str, Any]:
    # Introspect user intent and decide next actions
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": f"Previous context:\n{kb.get_recent_summaries(user_id)}"},
        {"role": "user", "content": f"Reflect on this query for planning: {query}"},
    ]
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.0,
        stream=False
    )
    # Expect JSON plan from reflection
    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        return {"plan": []}

# === Main answer function supporting multi-turn, tools, and reflection ===
async def answer(user_id: str, query: str) -> str:
    print(f"[agent] Incoming query from {user_id}: {query}")

    # --- Check for doc generation ---
    target_path = wants_docgen(query)
    if target_path:
        return await generate_doc_for_path(target_path)

    # --- Build context ---
    engine = ContextEngine(user_id=user_id)
    context = engine.build_context(query)
    print(f"[agent] Built context length: {len(context)} chars")

    # --- Reflection & planning ---
    plan = await reflect_and_plan(user_id, query)
    print(f"[agent] Reflection plan: {plan}")

    # --- Update conversation history ---
    history = conversation_history.setdefault(user_id, [])
    history.append({"role": "user", "content": query})
    
    # --- Compose messages with history and plan ---
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Context:\n{context}"},
        {"role": "assistant", "content": f"Plan: {json.dumps(plan)}"},
    ] + history

    # --- Call OpenAI with streaming enabled for long responses ---
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            stream=False,
            temperature=0.3,
            functions=[
                {
                    "name": "search_docs",
                    "description": "Search the local /docs/ for keywords",
                    "parameters": {"type": "object", "properties": {"query": {"type":"string"}, "user_id": {"type":"string"}}, "required":["query","user_id"]}
                },
                {
                    "name": "run_code_review",
                    "description": "Run static analysis on a source file path",
                    "parameters": {"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}
                }
            ],
            function_call="auto"
        )
        message = response.choices[0].message
        # --- Handle any function calls ---
        if message.get("function_call"):
            fname = message["function_call"]["name"]
            fargs = json.loads(message["function_call"]["arguments"])
            # Dispatch to local function implementations
            if fname == "search_docs":
                result = await search_docs(**fargs)
            elif fname == "run_code_review":
                result = await run_code_review(**fargs)
            else:
                result = {"error": f"Unknown function: {fname}"}
            return json.dumps(result)
        else:
            # Append assistant response to history
            history.append({"role": "assistant", "content": message.content})
            return message.content

    except Exception as e:
        print("❌ OpenAI call failed:", str(e))
        return f"[error] OpenAI call failed. {str(e)}"

# === Generate and queue documentation for a specific source file ===
async def generate_doc_for_path(rel_path: str) -> str:
    base = Path(__file__).resolve().parents[1]
    full_path = base / rel_path

    if not full_path.exists():
        return f"[error] File not found: {rel_path}"

    content = full_path.read_text()
    prompt = f"""
You are a helpful documentation bot. Read the following source file and write a useful Markdown documentation entry about what it is, what it does, and how it's used. Keep it concise and developer-friendly.

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

    async with httpx.AsyncClient() as http_client:
        res = await http_client.post(
            RAILWAY_URL,
            headers={"X-API-Key": RAILWAY_KEY},
            json=payload
        )
        if res.status_code == 200:
            return f"✅ Documentation queued to: {doc_path}"
        else:
            return f"❌ Failed to queue documentation: {res.status_code} {res.text}"
