# File: routes/github_proxy.py
import os, hmac, hashlib, json
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from github.GithubException import GithubException

router = APIRouter(prefix="/gh", tags=["github"])

# ── Auth (API_KEY or API_KEYS, comma-separated) ──────────────────────────
_API_KEYS = {tok.strip() for tok in (os.getenv("API_KEY","")+","+os.getenv("API_KEYS","")).split(",") if tok.strip()}

def require_api_key(authorization: str = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not any(hmac.compare_digest(token, k) for k in _API_KEYS):
        raise HTTPException(status_code=403, detail="Bad token")

@router.get("/debug/api-key")
def debug_api_key(authorization: Optional[str] = Header(None)):
    def sha8(s: str) -> str: return hashlib.sha256(s.encode()).hexdigest()[:8]
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
    server = next(iter(_API_KEYS), "")
    return {
        "keys_count": len(_API_KEYS),
        "server_key_len": len(server) if server else 0,
        "server_key_sha256_8": sha8(server) if server else None,
        "provided_len": len(provided),
        "provided_sha256_8": sha8(provided) if provided else None,
        "match": any(hmac.compare_digest(provided,k) for k in _API_KEYS),
    }

def _ga():
    try:
        from services import github_actions as ga
        return ga
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"github_actions import failed: {e}")

# ── Models ───────────────────────────────────────────────────────────────
class FileGetReq(BaseModel):
    repo: str
    path: str
    ref: Optional[str] = None

class FilePutReq(BaseModel):
    repo: str
    path: str
    content_b64: str
    message: str
    branch: str
    sha: Optional[str] = None

class BranchReq(BaseModel):
    repo: str
    base: str
    new_branch: str

class PRReq(BaseModel):
    repo: str
    title: str
    head: str
    base: str
    body: Optional[str] = None
    draft: bool = False

class ApplyDiffReq(BaseModel):
    repo: str
    base_branch: str
    new_branch: str
    commit_message: str
    diff: str
    allow_deletes: bool = False
    dry_run: bool = False

# ── Endpoints ────────────────────────────────────────────────────────────
@router.get("/health")
def gh_health(_: None = Depends(require_api_key)):
    ga = _ga()
    try:
        me = ga.gh.get_user().login  # type: ignore[attr-defined]
        return {"ok": True, "user": me, "allowlist": sorted(list(ga.ALLOWLIST))}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/repos")
def list_repos(_: None = Depends(require_api_key)):
    ga = _ga()
    return ga.list_repos()

@router.post("/file/get")
def file_get(req: FileGetReq, _: None = Depends(require_api_key)):
    ga = _ga()
    try:
        return ga.get_file(req.repo, req.path, req.ref)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        detail = e.data if getattr(e, "data", None) else {"message": str(e)}
        raise HTTPException(status_code=e.status or 500, detail=json.dumps(detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/file/put")
def file_put(req: FilePutReq, _: None = Depends(require_api_key)):
    ga = _ga()
    try:
        return ga.put_file(req.repo, req.path, req.content_b64, req.message, req.branch, req.sha)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        detail = e.data if getattr(e, "data", None) else {"message": str(e)}
        raise HTTPException(status_code=e.status or 500, detail=json.dumps(detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/branch/create")
def branch_create(req: BranchReq, _: None = Depends(require_api_key)):
    ga = _ga()
    try:
        return ga.create_branch(req.repo, req.base, req.new_branch)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        detail = e.data if getattr(e, "data", None) else {"message": str(e)}
        raise HTTPException(status_code=e.status or 500, detail=json.dumps(detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pr/open")
def pr_open(req: PRReq, _: None = Depends(require_api_key)):
    ga = _ga()
    try:
        return ga.open_pr(req.repo, req.title, req.head, req.base, req.body or "", req.draft)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        detail = e.data if getattr(e, "data", None) else {"message": str(e)}
        raise HTTPException(status_code=e.status or 500, detail=json.dumps(detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply-diff")
def apply_diff(req: ApplyDiffReq, _: None = Depends(require_api_key)):
    ga = _ga()
    try:
        return ga.apply_diff(
            req.repo,
            req.base_branch,
            req.new_branch,
            req.commit_message,
            req.diff,
            allow_deletes=req.allow_deletes,
            dry_run=req.dry_run,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except GithubException as e:
        detail = e.data if getattr(e, "data", None) else {"message": str(e)}
        raise HTTPException(status_code=e.status or 500, detail=json.dumps(detail))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
