from fastapi import APIRouter, Query, HTTPException
from pathlib import Path
from services.google_docs_sync import sync_google_docs

# Set up router with prefix and tag
router = APIRouter(prefix="/docs", tags=["docs"])

# Define path to the local docs directory
DOCS_PATH = Path(__file__).resolve().parents[1] / "docs"

@router.get("/list")
def list_docs():
    """
    Return a flat list of all .md and .txt files under /docs.
    This supports browsing or syncing documentation assets.
    """
    if not DOCS_PATH.exists():
        raise HTTPException(404, "Docs folder missing.")
    
    files = [
        str(p.relative_to(DOCS_PATH))
        for p in DOCS_PATH.rglob("*")
        if p.suffix in [".md", ".txt"]
    ]
    return {"files": sorted(files)}

@router.get("/view")
def view_doc(path: str = Query(..., description="Path relative to /docs")):
    """
    Return the contents of a single document by relative path.
    Used to preview or reference file content in Echo.
    """
    full_path = DOCS_PATH / path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(404, f"File not found: {path}")
    
    return {"content": full_path.read_text(encoding='utf-8')}

@router.post("/sync_google")
async def sync_google_docs_endpoint():
    """
    Syncs Google Docs from the 'Command_Center' Drive folder
    and stores them as Markdown files in /docs/imported.
    """
    try:
        synced = sync_google_docs()
        return {"status": "success", "synced_docs": synced}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
