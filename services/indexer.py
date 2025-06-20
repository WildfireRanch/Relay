
#services/indexer.py
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
embed_model = OpenAIEmbedding(model="text-embedding-3-large")
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
    """
    Recursively scans ROOT_DIRS, splits files into semantic chunks, embeds, and stores index.
    """
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
    index.storage_context.persist(persist_dir="./data/index")
    index.storage_context.persist(persist_dir=str(INDEX_DIR))
    print("Indexing complete!")

if __name__ == "__main__":
    index_directories()
services/kb.py
+4
-1

@@ -24,51 +24,54 @@ from llama_index.core import (
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.extractors import TitleExtractor
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.openai import OpenAIEmbedding

# ─── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.info("🔥 services.kb loaded")

# ─── Model configuration ───────────────────────────────────────────────────
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)
EMBED_MODEL = OpenAIEmbedding(model=MODEL_NAME, dimensions=3072)
if MODEL_NAME == "text-embedding-3-large":
    EMBED_MODEL = OpenAIEmbedding(model=MODEL_NAME, dimensions=3072)
else:
    EMBED_MODEL = OpenAIEmbedding(model=MODEL_NAME)

# ─── Index paths (hard-wired) ──────────────────────────────────────────────
PROJECT_ROOT = Path("/app")                                    # Railway image root
ENV_NAME     = os.getenv("ENV", "dev")                         # dev / prod / staging
INDEX_ROOT   = PROJECT_ROOT / "index" / ENV_NAME               # /app/index/<env>
INDEX_DIR    = INDEX_ROOT / MODEL_NAME                         # /app/index/<env>/<model>
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# Scrub any stale model folders (e.g., old Ada or double-nested dirs)
for path in INDEX_ROOT.iterdir():
    if path.is_dir() and path.name != MODEL_NAME:
        logger.warning("Removing stale index folder %s", path)
        shutil.rmtree(path, ignore_errors=True)

# ─── Ingestion pipeline ────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent
CODE_DIRS  = [ROOT.parent / p for p in ("src", "backend", "frontend")]
DOCS_DIR   = ROOT.parent / "docs"
CHUNK_SIZE, CHUNK_OVERLAP = 1024, 200

INGEST_PIPELINE = IngestionPipeline(
    transformations=[
        TitleExtractor(llm=None),                           # no async LLM
        SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP),
        EMBED_MODEL,