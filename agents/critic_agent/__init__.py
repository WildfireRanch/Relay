<<<<<<< HEAD
# File: agents/critic_agent/__init__.py

async def run(query: str, plan: dict, context: str = "", user_id: str = "system") -> dict:
    """
    Runs all critics against a given plan.
    """
    results = await run_critics(plan, query)
    return {
        "critics": results,
        "passes": all(c["passes"] for c in results)
    }
=======
from .run import run_critics

__all__ = ["run_critics"]
>>>>>>> 35e068f4e4ab81854ee7f4e9324f527514d5e4c2
