# File: services/indexer.py
# Purpose: Recursively index code and docs with tier metadata for prioritized semantic search.
# Stack: LlamaIndex, OpenAI, Python 3.12+
# Usage: Call index_directories() to scan, split, and embed all target files.

import os
import glob
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter
from services.config import INDEX_DIR

# ---- 1. Define priority tiers and associated paths ----
PRIORITY_INDEX_PATHS = [
    ("global", ["./docs/generated/global_context.md", "./docs/generated/global_context.auto.md"]),
    ("context", ["./context/"]),  # Cross-project overlays
    ("project_summary", ["./docs/PROJECT_SUMMARY.md", "./docs/RELAY_CODE_UPDATE.md", "./docs/context-commandcenter.md"]),
    ("project_docs", ["./docs/imported/", "./docs/kb/", "./docs/*.md"]),
    ("code", ["./services/", "./routes/", "./frontend/", "./src/", "./backend/"]),
]

# ---- 2. Embedding Model ----
model_name = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)
embed_model = OpenAIEmbedding(model=model_name, dimensions=3072 if model_name == "text-embedding-3-large" else None)

def index_directories():
    """
    Scans all PRIORITY_INDEX_PATHS, splits, tags with tier, and embeds for semantic search.
    """
    documents = []

    for tier, paths in PRIORITY_INDEX_PATHS:
        for path in paths:
            if path.endswith("/"):
                # Folder: Use LlamaIndex reader (recursively)
                if os.path.exists(path):
                    docs = SimpleDirectoryReader(path, recursive=True).load_data()
                    for d in docs:
                        d.metadata = d.metadata or {}
                        d.metadata["tier"] = tier
                    documents.extend(docs)
            elif "*" in path or path.endswith(".md"):
                # Glob/single file: add as individual Document
                for f in glob.glob(path):
                    if os.path.isfile(f):
                        with open(f, "r") as file:
                            text = file.read()
                        doc = Document(
                            text=text,
                            metadata={"tier": tier, "file_path": f}
                        )
                        documents.append(doc)

    # --- 3. Chunking ---
    code_splitter = CodeSplitter(max_chars=1024, chunk_lines=30, chunk_overlap=10)
    text_splitter = SentenceSplitter(max_chunk_size=1024)

    for doc in documents:
        # Use "file_path" (may be missing for some docs; fallback to empty string)
        file_path = doc.metadata.get('file_path', '')
        if file_path.endswith(('.py', '.js', '.ts', '.tsx', '.java', '.go', '.cpp')):
            doc.chunks = code_splitter.split(doc.text)
        else:
            doc.chunks = text_splitter.split(doc.text)

    # --- 4. Index & Persist ---
    print(f"Total documents indexed: {len(documents)}")
    index = VectorStoreIndex.from_documents(
        documents, embed_model=embed_model, show_progress=True
    )
    index.storage_context.persist(persist_dir="./data/index")
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("Indexing complete! Prioritized tiers saved.")

if __name__ == "__main__":
    index_directories()
