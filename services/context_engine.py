import os
from pathlib import Path
import services.kb as kb


class ContextEngine:
    """Gather runtime context from code, docs and logs."""

    def __init__(self, base: str | None = None):
        env_root = os.getenv("RELAY_PROJECT_ROOT")
        self.base = Path(env_root).resolve() if env_root else Path(base or Path.cwd())

    # === Keyword trigger ===
    @staticmethod
    def needs_code_context(query: str) -> bool:
        keywords = [
            "code",
            "review",
            "audit",
            "directory",
            "structure",
            "files",
            "access",
            "source",
        ]
        return any(kw in query.lower() for kw in keywords)

    # === Source code loader ===
    def read_source_files(self, roots=None, exts=None) -> str:
        if roots is None:
            roots = ["services"]
        if exts is None:
            exts = [".py", ".tsx", ".ts"]
        code = []
        excluded = ["node_modules", ".git", ".venv", "__pycache__", ".next"]
        for root in roots:
            path = self.base / root
            if not path.exists():
                continue
            for f in path.rglob("*"):
                if (
                    f.suffix in exts
                    and f.is_file()
                    and not any(ex in str(f) for ex in excluded)
                ):
                    try:
                        snippet = f"\n# File: {f.relative_to(self.base)}\n{f.read_text()}"
                        code.append(snippet)
                    except Exception:
                        continue
        return "\n".join(code)

    # === Documentation loader ===
    def read_docs(self, root="docs", exts=None) -> str:
        if exts is None:
            exts = [".md", ".txt"]
        path = self.base / root
        if not path.exists():
            return ""
        docs = []
        for f in path.rglob("*"):
            if f.suffix in exts and f.is_file():
                try:
                    snippet = f"\n# Doc: {f.relative_to(self.base)}\n{f.read_text()}"
                    docs.append(snippet)
                except Exception:
                    continue
        return "\n".join(docs)

    # === Session log summary ===
    def read_logs_summary(self) -> str:
        summary = self.base / "docs/generated/relay_context.md"
        if summary.exists():
            try:
                return summary.read_text()
            except Exception:
                return ""
        return ""

    # === High level context builder ===
    def build_context(self, query: str) -> str:
        if self.needs_code_context(query):
            code = self.read_source_files(
                [
                    "services",
                    "frontend/src/app",
                    "frontend/src/components",
                    "routes",
                    ".",
                ],
                exts=[".py", ".ts", ".tsx", ".json", ".env"],
            )
            docs = self.read_docs("docs")
            logs = self.read_logs_summary()
            return code[:5000] + "\n\n" + docs[:3000] + "\n\n" + logs[:1000]
        else:
            hits = kb.search(query, k=4)
            kb_context = (
                "\n\n".join(
                    f"[{i+1}] {h['path']}\n{h['snippet']}" for i, h in enumerate(hits)
                )
                or "No internal docs matched."
            )
            logs = self.read_logs_summary()
            return kb_context + "\n\n" + logs[:1000]
