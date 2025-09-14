# ──────────────────────────────────────────────────────────────────────────────
# File: tests/test_kb_embed_status.py
# ──────────────────────────────────────────────────────────────────────────────
import importlib
from pathlib import Path

def test_embed_all_empty_returns_status(tmp_path, monkeypatch):
    # Force a clean, empty index dir to exercise no-doc path safely
    cfg = importlib.import_module("services.kb")
    monkeypatch.setenv("INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("INDEX_ROOT", str(tmp_path / "index"))
    # Re-import to pick up env overrides (safer than reload in many runners)
    kb = importlib.reload(cfg)

    status = kb.embed_all(verbose=False)
    assert isinstance(status, dict)
    assert status.get("ok") is False
    assert "No valid docs" in (status.get("error") or "")
