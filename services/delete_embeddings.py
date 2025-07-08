# ──────────────────────────────────────────────────────────────────────────────
# File: delete_embeddings.py
# Directory: services
# Purpose: # Purpose: Manages the deletion of text embeddings from a search index, including file handling and index updates.
#
# Upstream:
#   - ENV: —
#   - Imports: numpy, openai, os, pickle, sys
#
# Downstream:
#   - —
#
# Contents:
#   - build_index()
#   - embed_text()
#   - iter_files()
#   - search_index()
# ──────────────────────────────────────────────────────────────────────────────

"""
Relay Embeddings Service
-----------------------------------
- Indexes project docs and code with OpenAI embeddings.
- Supports semantic search for agent context, docs, and Q&A.
- Simple CLI: build index, search index.
"""

import os
import openai
import numpy as np
import pickle

# Config (tweak paths/extensions as needed for your codebase)
SEARCH_DIRS = ["./docs", "./core", "./agents", "./services"]
EXTS = [".md", ".py", ".ts", ".tsx"]
EMBED_MODEL = "text-embedding-3-small"
EMBED_INDEX = "file_embeddings.pkl"

openai.api_key = os.environ.get("OPENAI_API_KEY")

def iter_files():
    for root in SEARCH_DIRS:
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if any(fname.endswith(ext) for ext in EXTS):
                    yield os.path.join(dirpath, fname)

def embed_text(text):
    """Get OpenAI embedding for input text."""
    resp = openai.embeddings.create(input=text, model=EMBED_MODEL)
    return np.array(resp.data[0].embedding)

def build_index():
    """Build and save the file embedding index."""
    index = []
    for fpath in iter_files():
        with open(fpath, encoding="utf-8", errors="ignore") as f:
            text = f.read()[:8000]  # Truncate for OpenAI limit
        emb = embed_text(text)
        index.append({
            "file": fpath,
            "embedding": emb,
            "snippet": text[:400]  # Preview for UI/context
        })
        print(f"Indexed: {fpath}")
    with open(EMBED_INDEX, "wb") as out:
        pickle.dump(index, out)
    print(f"Embedding index saved to {EMBED_INDEX}")

def search_index(query, top_k=5):
    """Return top_k most relevant files/snippets for a query."""
    with open(EMBED_INDEX, "rb") as f:
        index = pickle.load(f)
    q_emb = embed_text(query)
    scores = []
    for doc in index:
        sim = np.dot(q_emb, doc["embedding"])
        scores.append((sim, doc))
    scores.sort(reverse=True, key=lambda x: x[0])
    return [doc for _, doc in scores[:top_k]]

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        query = " ".join(sys.argv[2:]) or "relay agent context"
        results = search_index(query)
        for doc in results:
            print(f"{doc['file']}\n---\n{doc['snippet'][:200]}\n")
    else:
        build_index()
