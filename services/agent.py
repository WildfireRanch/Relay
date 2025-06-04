import os
import re
import json
from pathlib import Path
from openai import AsyncOpenAI
import services.kb as kb
import httpx

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

RAILWAY_KEY = os.getenv("API_KEY")
RAILWAY_URL = os.getenv("RAILWAY_URL", "https://relay.wildfireranch.us/control/queue_action")

# === System prompt that defines Relay's identity and context awareness ===
SYSTEM_PROMPT = """
You are Relay, the intelligent assistant for Bret's WildfireRanch pursuits including the solar shack project (solar powered bitcoin mining) and developing a business plan for a utility scale solar farm.
You have access to:

- Python source code in /services/
- React and Next.js components in /src/app/ and /src/components/
- FastAPI routes in /routes/
- A local knowledge base in /docs/

Use file paths in citations when helpful (e.g. src/components/LogsPanel/LogsPanel.tsx).
If the user asks about code, structure, or documentation, include relevant context.
You can generate and queue new documentation entries by calling /control/queue_action.
"""

# === Trigger logic to determine if code/doc context is needed ===
def needs_code_context(query: str) -> bool:
    keywords = ["code", "review", "audit", "directory", "structure", "files", "access", "source"]
    return any(kw in query.lower() for kw in keywords)

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

    if needs_code_context(query_lower):
        print("[agent] Context-aware mode triggered.")
        code = read_source_files(["services", "src/app", "src/components", "routes", "."], exts=[".py", ".ts", ".tsx", ".json", ".env"])
        docs = read_docs("docs/")
        context = code[:5000] + "\n\n" + docs[:3000]  # limit total context
        print(f"[agent] Combined context length: {len(context)}")
    else:
        hits = kb.search(query, k=4)
        context = "\n\n".join(
            f"[{i+1}] {h['path']}\n{h['snippet']}" for i, h in enumerate(hits)
        ) or "No internal docs matched."
        print(f"[agent] KB search context length: {len(context)}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Context:\n{context}"},
        {"role": "user", "content": query},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        stream=False,
        temperature=0.3,
    )

    return response.choices[0].message.content

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

# === Helper: Load source code from multiple folders ===
def read_source_files(roots=["services"], exts=[".py", ".tsx", ".ts"]):
    base = Path(__file__).resolve().parents[1]
    code = []
    excluded = ["node_modules", ".git", ".venv", "__pycache__", ".next"]

    for root in roots:
        path = base / root
        if not path.exists():
            print(f"[agent] Path does not exist: {path}")
            continue

        for f in path.rglob("*"):
            if (
                f.suffix in exts
                and f.is_file()
                and not any(ex in str(f) for ex in excluded)
            ):
                try:
                    content = f.read_text()
                    snippet = f"\n# File: {f.relative_to(base)}\n{content}"
                    code.append(snippet)
                except Exception as e:
                    print(f"[agent] Failed to read {f}: {e}")
                    continue
    return "\n".join(code)

# === Helper: Read plain text or markdown docs from /docs ===
def read_docs(root="docs", exts=[".md", ".txt"]):
    base = Path(__file__).resolve().parents[1]
    path = base / root
    if not path.exists():
        print(f"[agent] Docs path not found: {path}")
        return ""

    docs = []
    for f in path.rglob("*"):
        if f.suffix in exts and f.is_file():
            try:
                content = f.read_text()
                snippet = f"\n# Doc: {f.relative_to(base)}\n{content}"
                docs.append(snippet)
            except Exception as e:
                print(f"[agent] Failed to read doc {f}: {e}")
                continue
    return "\n".join(docs)
