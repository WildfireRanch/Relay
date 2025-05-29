import pathlib, sqlite3, json, os
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
DB_PATH  = ROOT / "kb.sqlite3"

_EMBED  = OpenAIEmbeddings(model="text-embedding-3-small",
                           openai_api_key=os.getenv("OPENAI_API_KEY"))
_SPLIT  = RecursiveCharacterTextSplitter(chunk_size=1024, chunk_overlap=128)

def _connect():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS docs(
            id TEXT PRIMARY KEY,
            path TEXT,
            chunk TEXT,
            embedding BLOB
        )""")
    return con

def embed_docs():
    con = _connect()
    for md in DOCS_DIR.rglob("*.md"):
        text = md.read_text("utf-8")
        chunks = _SPLIT.split_text(text)
        embeddings = _EMBED.embed_documents(chunks)
        for chunk, emb in zip(chunks, embeddings):
            uid = f"{md}:{hash(chunk)}"
            con.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,?)",
                        (uid, str(md), chunk, json.dumps(emb)))
    con.commit()
    con.close()

def search(query, k=4):
    con = _connect()
    q_emb = _EMBED.embed_query(query)
    rows = con.execute("""
        SELECT path, chunk FROM docs
        ORDER BY json_extract(embedding, '$')  -- naive; fine for small KB
    """).fetchmany(k)
    con.close()
    return [{"path": r[0], "snippet": r[1]} for r in rows]

# embed at startup
embed_docs()
