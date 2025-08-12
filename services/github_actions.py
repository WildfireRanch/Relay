# File: services/github_actions.py
import os
import base64
from typing import Optional, Dict, Any, Set

from github import Github
from github.GithubException import GithubException

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("Missing GITHUB_TOKEN")

# Short timeout so calls never hang the server
gh = Github(GITHUB_TOKEN, timeout=5)

ALLOWLIST: Set[str] = {
    s.strip() for s in os.getenv("REPO_ALLOWLIST", "").split(",") if s.strip()
}
AUTHOR_NAME  = os.getenv("COMMIT_AUTHOR_NAME", "Relay Bot")
AUTHOR_EMAIL = os.getenv("COMMIT_AUTHOR_EMAIL", "relay@wildfireranch.us")

def _repo(repo_full: str):
    if ALLOWLIST and repo_full not in ALLOWLIST:
        raise PermissionError(f"Repo {repo_full} not in REPO_ALLOWLIST")
    return gh.get_repo(repo_full)

def list_repos():
    # Avoid broad list calls; show the allowlist if present
    if ALLOWLIST:
        return [{"full_name": r} for r in sorted(ALLOWLIST)]
    return [{"full_name": r.full_name} for r in gh.get_user().get_repos()]

def get_file(repo_full: str, path: str, ref: Optional[str] = None) -> Dict[str, Any]:
    repo = _repo(repo_full)
    f = repo.get_contents(path, ref=ref) if ref else repo.get_contents(path)
    return {"sha": f.sha, "encoding": f.encoding, "content_b64": f.content}

def put_file(
    repo_full: str,
    path: str,
    content_b64: str,
    message: str,
    branch: str,
    sha: Optional[str] = None,
):
    repo = _repo(repo_full)
    content = base64.b64decode(content_b64)

    try:
        current = repo.get_contents(path, ref=branch)
        return repo.update_file(
            path,
            message,
            content,
            sha or current.sha,
            branch=branch,
            author={"name": AUTHOR_NAME, "email": AUTHOR_EMAIL},
            committer={"name": AUTHOR_NAME, "email": AUTHOR_EMAIL},
        )
    except GithubException:
        return repo.create_file(
            path,
            message,
            content,
            branch=branch,
            author={"name": AUTHOR_NAME, "email": AUTHOR_EMAIL},
            committer={"name": AUTHOR_NAME, "email": AUTHOR_EMAIL},
        )

def create_branch(repo_full: str, base: str, new_branch: str):
    repo = _repo(repo_full)
    base_ref = repo.get_git_ref(f"heads/{base}")
    return repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_ref.object.sha)

def open_pr(repo_full: str, title: str, head: str, base: str, body: str = "", draft: bool = False):
    repo = _repo(repo_full)
    pr = repo.create_pull(title=title, body=body, head=head, base=base, draft=draft)
    return {"number": pr.number, "html_url": pr.html_url}
