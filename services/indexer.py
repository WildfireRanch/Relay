# File: services/indexer.py
# Purpose: Recursively index code and docs, create semantic embeddings for search
# Stack: LlamaIndex, OpenAI, Python 3.12+
# Usage: Call index_directories() to scan, split, and embed all target files.

import os
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter
from services.kb import INDEX_DIR

# ---- Config ----
ROOT_DIRS = ["./src", "./backend", "./frontend", "./docs"]  # Edit as needed

# ---- Embedding Model ----
model_name = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)
if model_name == "text-embedding-3-large":
    embed_model = OpenAIEmbedding(model=model_name, dimensions=3072)
else:
    embed_model = OpenAIEmbedding(model=model_name)

def index_directories():
    """Rebuild the semantic index from ROOT_DIRS and persist to ``INDEX_DIR``."""
    documents = []
    for dir_path in ROOT_DIRS:
        if os.path.exists(dir_path):
            # Loads files recursively from dir_path
            docs = SimpleDirectoryReader(dir_path, recursive=True).load_data()
            documents.extend(docs)

    # Initialize chunkers for code vs. text
    code_splitter = CodeSplitter(max_chars=1024, chunk_lines=30, chunk_overlap=10)
    text_splitter = SentenceSplitter(max_chunk_size=1024)

    for doc in documents:
        # Choose splitter based on file type
        if doc.metadata['file_path'].endswith(('.py', '.js', '.ts', '.tsx', '.java', '.go', '.cpp')):
            doc.chunks = code_splitter.split(doc.text)
        else:
            doc.chunks = text_splitter.split(doc.text)

    # Build the vector index and persist to disk
    index = VectorStoreIndex.from_documents(
        documents, embed_model=embed_model, show_progress=True
    )
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("Indexing complete!")

if __name__ == "__main__":
    index_directories()
