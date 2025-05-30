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

async def answer(query: str) -> str:
    """Decide whether to search the KB or scan code, then call OpenAI."""
    
    # Check if user wants a code review
    if "review code" in query.lower() or "analyze code" in query.lower():
        context = read_source_files("services")[:8000] or "No code found."
    else:
        hits = kb.search(query, k=4)
        context = "\n\n".join(
            f"[{i+1}] {h['path']}\n{h['snippet']}" for i, h in enumerate(hits)
        ) or "No internal docs matched."

    # Prepare messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Context:\n{context}"},
        {"role": "user", "content": query},
    ]

    # GPT call (streaming off for now)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        stream=False,
        temperature=0.3,
    )

    return response.choices[0].message.content


def read_source_files(root=".", exts=[".py"]):
    """Walk the repo and return contents of source files in a single string."""
    files = Path(root).rglob("*")
    code = []
    for f in files:
        if f.suffix in exts and f.is_file() and "venv" not in str(f):
            try:
                content = f.read_text()
                snippet = f"\n# File: {f.relative_to(root)}\n{content}"
                code.append(snippet)
            except Exception:
                continue
    return "\n".join(code)
