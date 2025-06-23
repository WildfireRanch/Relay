# File: context_engine.py
# Directory: services/
# Purpose: Gather per-user runtime context from code, docs, logs, and the semantic knowledge base

import os
from pathlib import Path
from typing import List, Optional
import services.kb as kb

class ContextEngine:
    """
    Gather runtime context from code, docs, logs, and KB.
    Supports per-user memory and context for multi-turn conversations.
    """

    def __init__(self, user_id: str, base: Optional[str] = None):
        """
        Initialize with user-specific ID and project root.
        If RELAY_PROJECT_ROOT is set, use it; otherwise use provided base or cwd.
        """
        self.user_id = user_id
        env_root = os.getenv("RELAY_PROJECT_ROOT")
        self.base = Path(env_root).resolve() if env_root else Path(base or Path.cwd())

    @staticmethod
    def needs_code_context(query: str) -> bool:
        """
        Detect if the user's query implies code or documentation context is needed.
        """
        keywords = [
            "code", "review", "audit", "directory", "structure",
            "files", "access", "source", "refactor"
        ]
        return any(kw in query.lower() for kw in keywords)

    def read_source_files(
        self,
        roots: Optional[List[str]] = None,
        exts: Optional[List[str]] = None
    ) -> str:
        """
        Load and concatenate source files under specified roots and extensions.
        Excludes common build and dependency directories.
        """
        if roots is None:
            roots = ["services"]
        if exts is None:
            exts = [".py", ".tsx", ".ts"]
        excluded = {"node_modules", ".git", ".venv", "__pycache__", ".next"}
        snippets: List[str] = []
        for root in roots:
            path = self.base / root
            if not path.exists():
                continue
            for f in path.rglob("*"):
                if (
                    f.suffix in exts and
                    f.is_file() and
                    not any(ex in str(f) for ex in excluded)
                ):
                    try:
                        rel = f.relative_to(self.base)
                        snippet = f"# File: {rel}\n{f.read_text()}"
                        snippets.append(snippet)
                    except Exception as e:
                        print(f"[ContextEngine] Error reading file {f}: {e}")
                        continue
        return "\n".join(snippets)

    def read_docs(
        self,
        root: str = "docs",
        exts: Optional[List[str]] = None,
        exclude: Optional[List[str]] = None
    ) -> str:
        """
        Load and concatenate documentation files under the docs directory.
        Optionally skip files matching any string in ``exclude``.
        """
        if exts is None:
            exts = [".md", ".txt"]
        path = self.base / root
        if not path.exists():
            return ""
        snippets: List[str] = []
        for f in path.rglob("*"):
            if exclude and any(str(f).endswith(x) for x in exclude):
                continue
            if f.suffix in exts and f.is_file():
                try:
                    rel = f.relative_to(self.base)
                    snippet = f"# Doc: {rel}\n{f.read_text()}"
                    snippets.append(snippet)
                except Exception as e:
                    print(f"[ContextEngine] Error reading doc {f}: {e}")
                    continue
        return "\n".join(snippets)

    def read_logs_summary(self) -> str:
        """
        Load the relay context summary log for this user, if available.
        Falls back to generic summary if user-specific is missing.
        """
        summary_path = self.base / f"docs/generated/{self.user_id}_context.md"
        if summary_path.exists():
            try:
                return summary_path.read_text()
            except Exception as e:
                print(f"[ContextEngine] Error reading logs summary: {e}")
                return ""
        # Fallback to generic summary
        generic = self.base / "docs/generated/relay_context.md"
        return generic.read_text() if generic.exists() else ""

    def build_context(self, query: str) -> str:
        """
        Build a combined context string based on the query.
        Chooses between code/docs/logs versus KB snippets.
        Appends per-user summaries from KB as well.
        """
        logs = self.read_logs_summary()[:1000]

        manual = self.base / "docs/generated/global_context.md"
        auto = self.base / "docs/generated/global_context.auto.md"
        global_context = ""
        try:
            if manual.exists():
                global_context = f"# Doc: {manual.relative_to(self.base)}\n{manual.read_text()}"
            elif auto.exists():
                global_context = f"# Doc: {auto.relative_to(self.base)}\n{auto.read_text()}"
        except Exception as e:
            print(f"[ContextEngine] Error reading global context: {e}")

        # If code context needed, load code, docs, logs, and KB summary
        if self.needs_code_context(query):
            code = self.read_source_files(
                roots=[
                    "services",
                    "frontend/src/app",
                    "frontend/src/components",
                    "routes",
                    "."
                ],
                exts=[".py", ".ts", ".tsx", ".json", ".env"],
            )[:5000]

            docs_body = self.read_docs(
                "docs",
                exclude=["global_context.md", "global_context.auto.md"]
            )[:3000]

            docs = f"{global_context}\n\n{docs_body}" if global_context else docs_body

            kb_summary = kb.get_recent_summaries(self.user_id) if hasattr(kb, "get_recent_summaries") else ""
            context = f"{code}\n\n{docs}\n\nLogs:\n{logs}\n\nKB Summary:\n{kb_summary}"
        else:
            # Use KB search for semantic context (per-user if supported)
            try:
                hits = kb.search(query, user_id=self.user_id, k=4)
            except TypeError:
                # Fallback if kb.search doesn't accept user_id
                hits = kb.search(query, k=4)
            snippets = []
            for i, h in enumerate(hits):
                snippets.append(f"[{i+1}] {h['path']}\n{h['snippet']}")
            kb_context = "\n\n".join(snippets) or "No internal docs matched."
            kb_summary = kb.get_recent_summaries(self.user_id) if hasattr(kb, "get_recent_summaries") else ""
            if global_context:
                context = f"{kb_context}\n\n{global_context}\n\nLogs:\n{logs}\n\nKB Summary:\n{kb_summary}"
            else:
                context = f"{kb_context}\n\nLogs:\n{logs}\n\nKB Summary:\n{kb_summary}"
        return context
