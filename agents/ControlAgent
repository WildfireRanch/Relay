# File: agents/control_agent.py
# Purpose: Execute structured plans that trigger real-world scripts, toggles, or system actions
# Requirements: Secure execution environment. Relays only pre-approved commands.

from typing import Dict, Any
from core.logging import log_event


class ControlAgent:
    def __init__(self):
        # Define a registry of allowed commands and their execution bindings
        self.allowed_actions = {
            "restart_service": self.restart_service,
            "clear_cache": self.clear_cache,
            # Extend with real shell integrations, endpoints, or function hooks
        }

    async def run(self, query: str, context: str, user_id: str = "system") -> Dict[str, Any]:
        """
        Executes structured plan derived from user intent (typically from PlannerAgent).
        Expects `context` to include a JSON-style plan with one or more steps.
        """
        try:
            # In practice, you'd parse structured plan object here
            # For now assume the `context` is a single-step command string
            if context not in self.allowed_actions:
                log_event("control_agent_reject", {"user": user_id, "action": context})
                return {"error": f"Action '{context}' is not permitted."}

            result = await self.allowed_actions[context]()
            log_event("control_agent_success", {"user": user_id, "action": context})
            return {"result": result, "status": "executed", "action": context}

        except Exception as e:
            log_event("control_agent_error", {"user": user_id, "error": str(e)})
            return {"error": f"Failed to execute action: {str(e)}"}

    # === Example Mocked Actions ===
    async def restart_service(self):
        # Replace with actual restart logic
        return "Service restarted successfully."

    async def clear_cache(self):
        # Replace with actual cache clear logic
        return "Cache cleared."


# === Optional test entrypoint ===
if __name__ == "__main__":
    import asyncio

    agent = ControlAgent()
    result = asyncio.run(agent.run("restart_service", context="restart_service"))
    print(result)
