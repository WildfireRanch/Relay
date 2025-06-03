import os
import re
from pathlib import Path
from openai import AsyncOpenAI
import services.kb as kb

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === System prompt given to GPT before user input ===
SYSTEM_PROMPT = """
You are Echo, a concise but knowledgeable assistant for Bret's Solar-Shack
and infrastructure projects. Cite file paths when useful. If the user asks you
to review the source code, scan for potential issues, bugs, or improvements.
"""

# === Trigger logic for when to use code context ===
def matches_trigger(query: str) -> bool:
    q = query.lower().strip()
    patterns = [
        r"review.*code",
        r"analyze.*code",
        r"audit.*code",
        r"read.*source",
        r"source.*review",
    ]
    return any(re.search(p, q) for p in patterns)

# === Unified answer function (calls GPT-4) ===
async def answer(query: str) -> str:
    print(f"[agent] Incoming query: {query}")
    query_lower = query.lower()

    if matches_trigger(query_lower):
        print("[agent] Code review mode triggered.")
        code = read_source_files(["services", "src/app", "src/components"])
        docs = read_docs("docs/")
        context = code + "\n\n" + docs
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

# === Helper: Read source code from multiple directories ===
def read_source_files(roots=["services"], exts=[".py", ".tsx", ".ts"]):
    base = Path(__file__).resolve().parents[1]
    code = []

    for root in roots:
        path = base / root
        if not path.exists():
            print(f"[agent] Path does not exist: {path}")
            continue

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

# === Helper: Read docs as plain text from /docs ===
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
