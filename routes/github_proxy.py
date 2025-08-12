# File: routes/github_proxy.py
# 
from __future__ import annotations
import os
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from services import github_actions as ga
from github.GithubException import GithubException

router = APIRouter(prefix="/gh", tags=["github"])

API_KEY = os.getenv("API_KEY", "")

def require_api_key(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization.split(" ", 1)[1] != API_KEY:
        raise HTTPException(status_code=403, detail="Bad token")

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

@router.get("/repos")
def list_repos(_: None = Depends(require_api_key)):
    return ga.list_repos()

@router.post("/file/get")
def get_file(req: FileGetReq, _: None = Depends(require_api_key)):
    try:
        return ga.get_file(req.repo, req.path, req.ref)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        raise HTTPException(status_code=e.status or 500, detail=str(e.data or e))

@router.post("/file/put")
def put_file(req: FilePutReq, _: None = Depends(require_api_key)):
    try:
        return ga.put_file(req.repo, req.path, req.content_b64, req.message, req.branch, req.sha)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        raise HTTPException(status_code=e.status or 500, detail=str(e.data or e))

@router.post("/branch/create")
def create_branch(req: BranchReq, _: None = Depends(require_api_key)):
    try:
        return ga.create_branch(req.repo, req.base, req.new_branch)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        raise HTTPException(status_code=e.status or 500, detail=str(e.data or e))

@router.post("/pr/open")
def open_pr(req: PRReq, _: None = Depends(require_api_key)):
    try:
        return ga.open_pr(req.repo, req.title, req.head, req.base, req.body or "", req.draft)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except GithubException as e:
        raise HTTPException(status_code=e.status or 500, detail=str(e.data or e))
# ────────────────────────── GitHub Proxy ──────────────────────────