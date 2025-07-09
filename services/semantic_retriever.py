# ─────────────────────────────────────────────────────────────────────────────
# File: semantic_retriever.py
# Directory: services
# Purpose: # Purpose: Provide functionality to retrieve and handle semantic contexts using embeddings for natural language processing tasks.
#
# Upstream:
#   - ENV: —
#   - Imports: llama_index.core, llama_index.embeddings.openai, sys, traceback
#
# Downstream:
#   - services.context_injector
#
# Contents:
#   - get_semantic_context()
# ─────────────────────────────────────────────────────────────────────────────
from llama_index.core import load_index_from_storage, StorageContext
from llama_index.embeddings.openai import OpenAIEmbedding
import sys
import traceback

# === Configuration ===
INDEX_DIR = "./data/index"
EMBED_MODEL_NAME = "text-embedding-3-large"

# === Embedding Model and Storage Context ===
_embed_model = OpenAIEmbedding(model=EMBED_MODEL_NAME)
try:
    storage_context = StorageContext.from_defaults(persist_dir=INDEX_DIR)
    _index = load_index_from_storage(storage_context=storage_context, embed_model=_embed_model)
except Exception as e:
    print("LlamaIndex load_index_from_storage FAILED:")
    traceback.print_exc()
    sys.exit(1)

# === Main Retrieval Function ===
def get_semantic_context(query: str, top_k: int = 5) -> str:
    """
    Retrieves the top_k most semantically relevant code/docs chunks for the query.
    Returns concatenated context string (with file path/title if possible).
    """
    results = _index.query(query, top_k=top_k)
    if not results:
        return "No semantically relevant context found."
    lines = []
    for r in results:
        meta = r.metadata or {}
        title = meta.get("file_path") or meta.get("tier") or "Unknown Source"
        lines.append(f"### {title}\n{r.text.strip()}")
    return "\n\n".join(lines)
