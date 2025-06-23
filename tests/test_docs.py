import sys
import types
import asyncio
import pytest

# Stub external google modules so routes.docs can import without dependencies
google = types.ModuleType("google")
oauth2 = types.ModuleType("google.oauth2")
credentials_mod = types.ModuleType("google.oauth2.credentials")
credentials_mod.Credentials = object
oauth2.credentials = credentials_mod
google.oauth2 = oauth2
google_auth_oauthlib = types.ModuleType("google_auth_oauthlib")
google_auth_oauthlib.flow = types.SimpleNamespace(InstalledAppFlow=object)
google.auth = types.ModuleType("google.auth")
google.auth.transport = types.ModuleType("google.auth.transport")
google.auth.transport.requests = types.SimpleNamespace(Request=object)
googleapiclient = types.ModuleType("googleapiclient")
googleapiclient.discovery = types.SimpleNamespace(build=lambda *a, **k: None)
markdownify = types.ModuleType("markdownify")
markdownify.markdownify = lambda x: x
sys.modules.setdefault("google", google)
sys.modules.setdefault("google.oauth2", oauth2)
sys.modules.setdefault("google.oauth2.credentials", credentials_mod)
sys.modules.setdefault("google_auth_oauthlib", google_auth_oauthlib)
sys.modules.setdefault("google_auth_oauthlib.flow", google_auth_oauthlib.flow)
sys.modules.setdefault("google.auth", google.auth)
sys.modules.setdefault("google.auth.transport", google.auth.transport)
sys.modules.setdefault("google.auth.transport.requests", google.auth.transport.requests)
sys.modules.setdefault("googleapiclient", googleapiclient)
sys.modules.setdefault("googleapiclient.discovery", googleapiclient.discovery)
sys.modules.setdefault("markdownify", markdownify)

# Stub services.kb to avoid heavy deps
kb_stub = types.ModuleType("services.kb")
kb_stub.api_reindex = lambda: {"status": "ok"}
sys.modules.setdefault("services.kb", kb_stub)

from routes import docs as docs_routes
list_docs = docs_routes.list_docs
sync_docs = docs_routes.sync_docs
refresh_kb = docs_routes.refresh_kb
full_sync = docs_routes.full_sync


def test_docs_list():
    data = asyncio.run(list_docs(category="all", limit=100))
    assert "files" in data
    assert isinstance(data["files"], list)


def test_docs_list_limit_enforced():
    limit = 3
    data = asyncio.run(list_docs(category="all", limit=limit))
    assert len(data["files"]) <= limit


def test_docs_sync(monkeypatch):
    monkeypatch.setattr(docs_routes, "sync_google_docs", lambda: ["foo.md"])
    data = asyncio.run(sync_docs())
    assert data == {"synced_docs": ["foo.md"]}


def test_refresh_kb(monkeypatch):
    monkeypatch.setattr(docs_routes.kb, "api_reindex", lambda: {"status": "ok"})
    data = asyncio.run(refresh_kb())
    assert data == {"status": "ok"}


def test_full_sync(monkeypatch):
    monkeypatch.setattr(docs_routes, "sync_google_docs", lambda: ["bar.md"])
    monkeypatch.setattr(docs_routes.kb, "api_reindex", lambda: {"status": "ok"})
    data = asyncio.run(full_sync())
    assert data == {"synced_docs": ["bar.md"], "kb": {"status": "ok"}}
