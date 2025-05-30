import os
from pathlib import Path
from openai import AsyncOpenAI
import services.kb as kb

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are Echo, a concise but knowledgeable assistant for Bret's Solar-Shack
and infrastructure projects. Cite file paths when useful. If the user asks you
to review the source code, scan for potential issues, bugs, or improvements.
"""

TRIGGERS = [
    "review code",
    "analyze code",
    "analyze source",
    "audit code",
    "review the python",
    "read the source code"
]

async def answer(query: str) -> str:
    """Handle KB-based questions or code review requests."""
    query_lower = query.lower()

    if any(p in query_lower for p in TRIGGERS):
        print("[agent] Code review mode triggered.")
        context = read_source_files("services")[:8000] or "No code found."
        print(f"[agent] Code context length: {len(context)}")
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


def read_source_files(root="services", exts=[".py"]):
    """Read .py files under the given path, skipping venv and errors."""
    base = Path(__file__).resolve().parents[1]
    path = base / root
    if not path.exists():
        print(f"[agent] Path does not exist: {path}")
        return ""

    code = []
    for f in path.rglob("*"):
        if f.suffix in exts and f.is_file() and "venv" not in str(f):
            try:
                content = f.read_text()
                snippet = f"\n# File: {f.relative_to(base)}\n{content}"
                code.append(snippet)
            except Exception as e:
                print(f"[agent] Failed to read {f}: {e}")
                continue
    return "\n".join(code)
