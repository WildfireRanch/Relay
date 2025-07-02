# services/semantic_retriever.py

from llama_index.core import load_index_from_storage
from llama_index.embeddings.openai import OpenAIEmbedding

# --- Load index once at startup ---
INDEX_DIR = "./data/index"
_embed_model = OpenAIEmbedding(model="text-embedding-3-large")  # Keep in sync with your index
_index = load_index_from_storage(persist_dir=INDEX_DIR, embed_model=_embed_model)

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
