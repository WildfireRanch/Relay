# File: context_engine.py
# Directory: services/
# Purpose: Gather per-user runtime context for agent prompt using tiered, prioritized semantic search

import os
from pathlib import Path
from typing import List, Optional, Tuple
from functools import lru_cache
import services.kb as kb

_CACHED_ENV_ROOT = os.getenv("RELAY_PROJECT_ROOT")

class ContextEngine:
    """
    Gather runtime context from code, docs, overlays, and KB using prioritized tiered search.
    Supports per-user memory and context for multi-turn conversations.
    """

    def __init__(self, user_id: str, base: Optional[str] = None):
        """
        Initialize with user-specific ID and project root.
        If RELAY_PROJECT_ROOT is set, use it; otherwise use provided base or cwd.
        Clears caches if the environment project root has changed.
        """
        self.user_id = user_id
        env_root = os.getenv("RELAY_PROJECT_ROOT")
        if env_root != _CACHED_ENV_ROOT:
            self.clear_cache()
            globals()["_CACHED_ENV_ROOT"] = env_root
        self.base = Path(env_root).resolve() if env_root else Path(base or Path.cwd())

    def build_context(
    self,
    query: str,
    k: int = 8,
    score_threshold: Optional[float] = None,
    return_debug: bool = False,
    )-> str | dict:

        """
        Build a tiered, labeled agent context window using prioritized semantic search.
        Optionally filter out low-scoring KB hits.

        Returns a prompt like:
            # [Global Context]
            ...
            # [Overlay: context-btc.md]
            ...
            # [Project Summary: PROJECT_SUMMARY.md]
            ...
            # [Code: services/miner.py]
            ...
        """
        # 1. Priority-aware semantic search (returns ordered, tier-labeled blocks)
        results = kb.search(
            query,
            k=k,
            user_id=self.user_id,
            score_threshold=score_threshold,
        )
        blocks = []
        for r in results:
            # Compose a readable label based on tier
            label = ""
            if r["tier"] == "global":
                label = "# [Global Context]"
            elif r["tier"] == "context":
                label = f"# [Overlay: {r['title']}]"
            elif r["tier"] == "project_summary":
                label = f"# [Project Summary: {r['title']}]"
            elif r["tier"] == "project_docs":
                label = f"# [Project Doc: {r['title']}]"
            elif r["tier"] == "code":
                label = f"# [Code: {r['title']}]"
            else:
                label = f"# [Other: {r['title']}]"
            snippet = r['snippet'][:2000]  # Tune/truncate as needed for context window
            blocks.append(f"{label}\n{snippet}")

        # Optionally: add logs/session memory as an extra tier
        # logs = self.read_logs_summary()[:1000]
        # blocks.append(f"# [Session Memory]\n{logs}")

        prompt = "\n\n".join(blocks)
        return prompt

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached results for docs and source file reads."""
        cls._cached_read_source_files.cache_clear()
        cls._cached_read_docs.cache_clear()

    # --- Old methods (still used in tests; now cached) ---------------------
    @staticmethod
    @lru_cache(maxsize=None)
    def _cached_read_source_files(base: str, roots: Tuple[str, ...], exts: Tuple[str, ...]) -> str:
        base_path = Path(base)
        search_roots = [base_path / r for r in roots] if roots else [base_path]
        exts = exts or (".py",)
        contents: List[str] = []
        for root in search_roots:
            for ext in exts:
                for f in root.rglob(f"*{ext}"):
                    try:
                        contents.append(f.read_text())
                    except Exception:
                        continue
        return "\n".join(contents)

    @staticmethod
    @lru_cache(maxsize=None)
    def _cached_read_docs(base: str, root: str, exts: Tuple[str, ...], exclude: Tuple[str, ...]) -> str:
        base_path = Path(base) / root
        exts = exts or (".md",)
        exclude_paths = {base_path / e for e in exclude}
        contents: List[str] = []
        for ext in exts:
            for f in base_path.rglob(f"*{ext}"):
                if any(str(f).startswith(str(p)) for p in exclude_paths):
                    continue
                try:
                    contents.append(f.read_text())
                except Exception:
                    continue
        return "\n".join(contents)

    def read_source_files(self, roots: Optional[List[str]] = None, exts: Optional[List[str]] = None) -> str:
        return self._cached_read_source_files(str(self.base), tuple(roots or ()), tuple(exts or ()))

    def read_docs(
        self, root: str = "docs", exts: Optional[List[str]] = None, exclude: Optional[List[str]] = None
    ) -> str:
        return self._cached_read_docs(str(self.base), root, tuple(exts or ()), tuple(exclude or ()))

    def read_additional_context_roots(self, roots: Optional[List[str]] = None, exts: Optional[List[str]] = None) -> str:
        return ""  # Now handled by LlamaIndex tiered search

    def read_logs_summary(self) -> str:
        """
        (Optional) Load session/memory log if you want to add as extra context.
        """
        summary_path = self.base / f"docs/generated/{self.user_id}_context.md"
        if summary_path.exists():
            try:
                return summary_path.read_text()
            except Exception:
                return ""
        generic = self.base / "docs/generated/relay_context.md"
        return generic.read_text() if generic.exists() else ""
