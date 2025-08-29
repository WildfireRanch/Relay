# File: tests/test_main_ready.py
# Directory: tests
# Purpose: Validate main.py readiness behavior (local vs prod), request-id header, and version.

import importlib
import os
import pytest
from httpx import AsyncClient


async def _load_app(monkeypatch, env_value: str, with_keys: bool):
    """
    Reload main.py under a given ENV and with/without required secrets.
    Returns (module, app) ready to use with an ASGI test client.
    """
    # Ensure a clean import
    if "main" in list(importlib.sys.modules.keys()):
        importlib.invalidate_caches()
        importlib.sys.modules.pop("main")

    # Set environment before import so module-level ENV_NAME is correct
    monkeypatch.setenv("ENV", env_value)
    # Ensure directories presence so ready() doesn't fail on paths
    base = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(base, ".."))
    for sub in ("docs/imported", "docs/generated", "data/index"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    # Required keys (API_KEY, OPENAI_API_KEY)
    if with_keys:
        monkeypatch.setenv("API_KEY", "test-api-key")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    else:
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Import (wires app with middlewares/routers)
    main = importlib.import_module("main")
    return main, main.app


@pytest.mark.asyncio
async def test_ready_local_discloses_and_passes(monkeypatch):
    main, app = await _load_app(monkeypatch, env_value="local", with_keys=True)
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/ready")
        assert r.status_code == 200
        j = r.json()
        # In local, details should include the specific keys and dirs
        assert "details" in j and isinstance(j["details"], dict)
        assert j["details"].get("API_KEY") is True
        assert j["details"].get("OPENAI_API_KEY") is True
        assert j["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_prod_redacts_details(monkeypatch):
    main, app = await _load_app(monkeypatch, env_value="prod", with_keys=True)
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/ready")
        assert r.status_code == 200
        j = r.json()
        # In prod, details should be redacted/empty
        assert "details" in j and j["details"] == {}
        assert j["status"] == "ok"


@pytest.mark.asyncio
async def test_request_id_header_present(monkeypatch):
    main, app = await _load_app(monkeypatch, env_value="prod", with_keys=True)
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/")
        assert r.status_code == 200
        # Middleware should attach X-Request-Id
        assert r.headers.get("X-Request-Id")


@pytest.mark.asyncio
async def test_version_endpoint(monkeypatch):
    main, app = await _load_app(monkeypatch, env_value="prod", with_keys=True)
    async with AsyncClient(app=app, base_url="http://test") as client:
        r = await client.get("/version")
        assert r.status_code == 200
        j = r.json()
        # Should always return keys even if git is unavailable
        assert "git_commit" in j
        assert "env" in j
