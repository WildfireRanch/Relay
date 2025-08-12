# File: services/github_actions.py
import os
import base64
from typing import Optional, Dict, Any, Set

from github import Github
from github.GithubException import GithubException
from github.InputGitAuthor import InputGitAuthor

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("Missing GITHUB_TOKEN")

# Short timeout so calls never hang the server (can override via env)
gh = Github(GITHUB_TOKEN, timeout=float(os.getenv("GITHUB_TIMEOUT", "5")))

ALLOWLIST: Set[str] = {
    s.strip() for s in os.getenv("REPO_ALLOWLIST", "").split(",") if s.strip()
}
AUTHOR_NAME = os.getenv("COMMIT_AUTHOR_NAME", "Relay Bot")
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
    """
    Create or update a file on a branch.
    - Accepts base64 content; converts to UTF-8 string (PyGithub expects str).
    - Uses InputGitAuthor for author/committer to avoid silent failures.
    """
    repo = _repo(repo_full)

    # Decode to *string* (PyGithub wants str, not bytes)
    content_bytes = base64.b64decode(content_b64)
    content_str = content_bytes.decode("utf-8", errors="replace")

    author = InputGitAuthor(AUTHOR_NAME, AUTHOR_EMAIL)

    try:
        # If file exists on that branch → update
        current = repo.get_contents(path, ref=branch)
        return repo.update_file(
            path=path,
            message=message,
            content=content_str,
            sha=sha or current.sha,
            branch=branch,
            author=author,
            committer=author,
        )
    except GithubException as e:
        # 404 = file not found on that branch → create
        if getattr(e, "status", None) == 404:
            return repo.create_file(
                path=path,
                message=message,
                content=content_str,
                branch=branch,
                author=author,
                committer=author,
            )
        # Any other GitHub error: re-raise so the router can surface details
        raise

def create_branch(repo_full: str, base: str, new_branch: str):
    repo = _repo(repo_full)
    base_ref = repo.get_git_ref(f"heads/{base}")
    return repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_ref.object.sha)

def open_pr(
    repo_full: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
    draft: bool = False,
):
    repo = _repo(repo_full)
    pr = repo.create_pull(title=title, body=body, head=head, base=base, draft=draft)
    return {"number": pr.number, "html_url": pr.html_url}
