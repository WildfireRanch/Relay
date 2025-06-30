# File: agents/critic_agent/__init__.py

from .run import run_critics

__all__ = ["run_critics"]

async def run(query: str, plan: dict, context: str = "", user_id: str = "system") -> dict:
    """
    Runs all critics against a given plan.
    """
    results = await run_critics(plan, query)
    return {
        "critics": results,
        "passes": all(c["passes"] for c in results)
    }
