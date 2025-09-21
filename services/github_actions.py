"""
File: services/github_actions.py
Purpose: Pure service helpers for GitHub operations using PyGithub.

Exports (used by routes/github_proxy.py):
  - gh: Github client
  - ALLOWLIST: set[str] of allowed repos ("owner/name")
  - list_repos() -> dict
  - get_file(repo, path, ref=None) -> dict
  - put_file(repo, path, content_b64, message, branch, sha=None) -> dict
  - create_branch(repo, base, new_branch) -> dict
  - open_pr(repo, title, head, base, body, draft=False) -> dict
  - apply_diff(...): placeholder raising ValueError
"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, Optional, Set

from github import Github
from github.GithubException import GithubException


def _token_present() -> bool:
    return bool(os.getenv("GITHUB_TOKEN"))


# Initialize a module-level Github client (unauth if token missing)
gh = Github(os.getenv("GITHUB_TOKEN"))


def _allowlist_from_env() -> Set[str]:
    raw = os.getenv("GITHUB_ALLOWLIST", "").strip()
    items = {s.strip() for s in raw.split(",") if s.strip()}
    # Add OWNER/REPO if present
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")
    if owner and repo:
        items.add(f"{owner}/{repo}")
    return items or set()


ALLOWLIST: Set[str] = _allowlist_from_env()


def _assert_ready(write: bool = False) -> None:
    if write and not _token_present():
        raise RuntimeError("GITHUB_TOKEN is required for write operations")


def _repo_guard(name: str):
    if ALLOWLIST and name not in ALLOWLIST:
        raise PermissionError(f"repo not allowlisted: {name}")


def list_repos() -> Dict[str, Any]:
    _assert_ready(write=False)
    try:
        if not ALLOWLIST:
            # Fallback: list user repos (may be large)
            repos = [r.full_name for r in gh.get_user().get_repos()]  # type: ignore[attr-defined]
        else:
            repos = sorted(list(ALLOWLIST))
        return {"repos": repos}
    except GithubException as e:
        return {"error": getattr(e, "data", str(e))}


def get_file(repo: str, path: str, ref: Optional[str] = None) -> Dict[str, Any]:
    _assert_ready(write=False)
    _repo_guard(repo)
    rep = gh.get_repo(repo)  # type: ignore[attr-defined]
    content = rep.get_contents(path, ref=ref) if ref else rep.get_contents(path)
    if isinstance(content, list):
        return {
            "type": "dir",
            "entries": [{"name": c.name, "path": c.path, "type": c.type, "sha": c.sha, "size": getattr(c, "size", None)} for c in content],
        }
    # file
    text = base64.b64decode(content.content or b"").decode("utf-8", errors="ignore")
    return {"type": "file", "path": content.path, "sha": content.sha, "size": getattr(content, "size", None), "content": text}


def put_file(repo: str, path: str, content_b64: str, message: str, branch: str, sha: Optional[str] = None) -> Dict[str, Any]:
    _assert_ready(write=True)
    _repo_guard(repo)
    rep = gh.get_repo(repo)  # type: ignore[attr-defined]
    if sha:
        res = rep.update_file(path, message, base64.b64decode(content_b64), sha, branch=branch)
    else:
        res = rep.create_file(path, message, base64.b64decode(content_b64), branch=branch)
    # PyGithub returns a dict with content and commit keys
    commit = res.get("commit") if isinstance(res, dict) else getattr(res, "commit", None)
    sha_out = getattr(commit, "sha", None) if commit else None
    return {"commit_sha": sha_out}


def create_branch(repo: str, base: str, new_branch: str) -> Dict[str, Any]:
    _assert_ready(write=True)
    _repo_guard(repo)
    rep = gh.get_repo(repo)  # type: ignore[attr-defined]
    base_ref = rep.get_git_ref(f"heads/{base}")
    rep.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_ref.object.sha)
    return {"ref": new_branch, "base": base}


def open_pr(repo: str, title: str, head: str, base: str, body: str, draft: bool = False) -> Dict[str, Any]:
    _assert_ready(write=True)
    _repo_guard(repo)
    rep = gh.get_repo(repo)  # type: ignore[attr-defined]
    pr = rep.create_pull(title=title, head=head, base=base, body=body, draft=draft)
    return {"number": pr.number, "title": pr.title, "head": pr.head.ref, "base": pr.base.ref}


def apply_diff(
    repo: str,
    base_branch: str,
    new_branch: str,
    commit_message: str,
    diff: str,
    *,
    allow_deletes: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    # Placeholder: not implemented yet.
    raise ValueError("apply_diff is not implemented in this service")
