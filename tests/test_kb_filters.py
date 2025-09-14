# ──────────────────────────────────────────────────────────────────────────────
# File: tests/test_kb_filters.py
# ──────────────────────────────────────────────────────────────────────────────
import importlib
from pathlib import Path

def test_should_index_file_filters_tmp(tmp_path):
    kb = importlib.import_module("services.kb")

    (tmp_path / "node_modules").mkdir()
    big = tmp_path / "big.txt"
    big.write_text("x" * (kb.MAX_FILE_SIZE_MB * 1024 * 1024 + 1))
    ok_md = tmp_path / "note.md"
    ok_md.write_text("# hello")
    lock = tmp_path / "yarn.lock"
    lock.write_text("lock")

    in_ignored_folder = tmp_path / "node_modules" / "a.py"
    in_ignored_folder.write_text("print(1)")

    assert kb.should_index_file(str(ok_md), tier="project_docs") is True
    assert kb.should_index_file(str(lock), tier="project_docs") is False
    assert kb.should_index_file(str(big), tier="project_docs") is False
    assert kb.should_index_file(str(in_ignored_folder), tier="code") is False

def test_code_tier_extensions(tmp_path):
    kb = importlib.import_module("services.kb")
    p = tmp_path / "app.py"
    p.write_text("print(1)")
    assert kb.should_index_file(str(p), tier="code") is True
    q = tmp_path / "img.png"
    q.write_text("x")
    assert kb.should_index_file(str(q), tier="code") is False
