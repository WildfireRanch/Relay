# ──────────────────────────────────────────────────────────────────────────────
# File: context_engine.py
# Directory: services
# Purpose: # Purpose: Manages the creation and lifecycle of context objects, including caching mechanisms, for the application.
#
# Upstream:
#   - ENV: —
#   - Imports: services.context_injector
#
# Downstream:
#   - routes.docs
#   - services.agent
#
# Contents:
#   - ContextEngine()
#   - build()
#   - clear_cache()

# ──────────────────────────────────────────────────────────────────────────────

from services.context_injector import build_context

class ContextEngine:
    """
    Facade for agent context building, cache clearing, and future extensions.
    Call anywhere as ContextEngine.build(...) or ContextEngine.clear_cache().
    """

    @staticmethod
    async def build(
        query: str, 
        files: list[str], 
        topics: list[str] = [], 
        debug: bool = False
    ):
        """
        Build multi-source context for agent prompts.
        """
        return await build_context(query, files, topics, debug)

    @staticmethod
    def clear_cache():
        """
        Placeholder for clearing context/semantic/graph/global caches.
        Expand as needed for production.
        """
        pass
