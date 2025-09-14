# ──────────────────────────────────────────────────────────────────────────────
# File: services/__init__.py
# Purpose: Package marker with NO eager submodule imports (prevents circulars).
# ──────────────────────────────────────────────────────────────────────────────
__all__: list[str] = []

# Optional: enable lazy submodule loading if you want (kept off by default).
# import importlib
# def __getattr__(name: str):
#     if name in {"kb", "indexer", "config", "embeddings"}:
#         return importlib.import_module(f"{__name__}.{name}")
#     raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
