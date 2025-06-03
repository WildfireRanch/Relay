# services/kb.py
import pathlib, sqlite3, json
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from services.settings import assert_env
import numpy as np
import hashlib
from datetime import datetime

# === Paths ===
ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
DB_PATH  = ROOT / "kb.sqlite3"

# === Initialize Embedding + Splitter ===
OPENAI_API_KEY = assert_env("OPENAI_API_KEY", "Used for LangChain embedding")
_EMBED  = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=OPENAI_API_KEY)
_SPLIT  = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=128)

# === DB Setup ===
def _connect():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS docs(
            id TEXT PRIMARY KEY,
            path TEXT,
            chunk TEXT,
            embedding BLOB,
            title TEXT,
            updated TEXT
        )
    """)
    return con

# === Embed all Markdown docs into the KB ===
def embed_docs():
    con = _connect()
    for md in DOCS_DIR.rglob("*.md"):
        text = md.read_text("utf-8")
        chunks = _SPLIT.split_text(text)
        embeddings = _EMBED.embed_documents(chunks)
        title = md.stem.replace("_", " ").title()
        updated = datetime.fromtimestamp(md.stat().st_mtime).isoformat()
        for chunk, emb in zip(chunks, embeddings):
            uid = hashlib.sha256((str(md) + chunk).encode()).hexdigest()
            con.execute(
                "INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?)",
                (uid, str(md), chunk, json.dumps(emb), title, updated)
            )
    con.commit()
    con.close()

# === Vector similarity search ===
def cosine_similarity(v1, v2):
    v1, v2 = np.array(v1), np.array(v2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

def search(query, k=4):
    con = _connect()
    q_emb = _EMBED.embed_query(query)
    rows = con.execute("SELECT path, chunk, embedding, title, updated FROM docs").fetchall()
    results = []
    for path, chunk, emb_json, title, updated in rows:
        sim = cosine_similarity(q_emb, json.loads(emb_json))
        results.append((sim, path, chunk, title, updated))
    con.close()
    top = sorted(results, key=lambda r: r[0], reverse=True)[:k]
    return [
        {"path": path, "title": title, "snippet": chunk, "updated": updated, "similarity": sim}
        for sim, path, chunk, title, updated in top
    ]

# === Run embedding when invoked directly ===
if __name__ == "__main__":
    embed_docs()
