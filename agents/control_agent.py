# File: agents/control_agent.py
# Purpose: Execute structured plans that trigger real-world scripts, toggles, or system actions
# Directory: agents/
# Notes:
#   - Only executes actions from an allowlist (`allowed_actions`)
#   - Each action is an async function to allow network/shell integration
#   - Designed to be safely called from MCP as: control_agent.run(...)

from typing import Dict, Any
from core.logging import log_event


class ControlAgent:
    def __init__(self):
        """
        Initialize the action registry with a safe allowlist.
        Only explicitly listed actions can be invoked by plans.
        """
        self.allowed_actions = {
            "restart_service": self.restart_service,
            "clear_cache": self.clear_cache,
            # TODO: Add more actions (e.g., relay toggles, shell scripts, API hooks)
        }

    async def run(self, query: str, context: str, user_id: str = "system") -> Dict[str, Any]:
        """
        Executes a structured action. Expects the `context` to contain the action key (e.g., 'restart_service').

        Parameters:
            query (str): The original user query (for logging).
            context (str): The parsed action key or structured step to execute.
            user_id (str): Identifier for auditing/logging.

        Returns:
            Dict[str, Any]: Result or error message from the action execution.
        """
        try:
            if context not in self.allowed_actions:
                log_event("control_agent_reject", {
                    "user": user_id,
                    "action": context,
                    "reason": "Not in allowlist"
                })
                return {"error": f"Action '{context}' is not permitted."}

            result = await self.allowed_actions[context]()
            log_event("control_agent_success", {
                "user": user_id,
                "action": context,
                "result": result
            })

            return {
                "result": result,
                "status": "executed",
                "action": context
            }

        except Exception as e:
            log_event("control_agent_error", {
                "user": user_id,
                "action": context,
                "error": str(e)
            })
            return {"error": f"Failed to execute action: {str(e)}"}

    # === Mocked Actions — replace with real logic ===

    async def restart_service(self) -> str:
        """
        Simulated restart of a service (e.g., relay, backend daemon).
        """
        # TODO: Replace with actual restart command or script trigger
        return "Service restarted successfully."

    async def clear_cache(self) -> str:
        """
        Simulated cache clear.
        """
        # TODO: Replace with actual cache clear operation
        return "Cache cleared."


# === Exported instance for use in MCP and other agents ===
control_agent = ControlAgent()

# === Optional CLI test runner ===
if __name__ == "__main__":
    import asyncio

    async def test():
        agent = ControlAgent()
        result = await agent.run("restart_service", context="restart_service")
        print("Result:", result)

    asyncio.run(test())
