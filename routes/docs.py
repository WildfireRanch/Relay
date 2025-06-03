from fastapi import APIRouter, Query, HTTPException
from pathlib import Path

router = APIRouter(prefix="/docs", tags=["docs"])

DOCS_PATH = Path(__file__).resolve().parents[1] / "docs"

@router.get("/list")
def list_docs():
    """Return a flat list of all .md and .txt docs under /docs."""
    if not DOCS_PATH.exists():
        raise HTTPException(404, "Docs folder missing.")
    files = [str(p.relative_to(DOCS_PATH)) for p in DOCS_PATH.rglob("*") if p.suffix in [".md", ".txt"]]
    return {"files": sorted(files)}

@router.get("/view")
def view_doc(path: str = Query(..., description="Path relative to /docs")):
    """Return the contents of a single doc."""
    full_path = DOCS_PATH / path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(404, f"File not found: {path}")
    return {"content": full_path.read_text()}
