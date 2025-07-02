# File: services/context_engine.py
# Purpose: Drop-in ContextEngine class for all context operations (build, clear cache, etc.)

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
