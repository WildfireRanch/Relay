# File: agents/control_agent.py
# Purpose: Securely execute structured plans as shell actions or toggles
# Directory: agents/

from typing import Dict, Any
from core.logging import log_event
import subprocess
import shlex


class ControlAgent:
    def __init__(self):
        """
        Register all allowed actions. Only these can be triggered.
        Each maps to an async method on this class.
        """
        self.allowed_actions = {
            "restart_service": self.restart_service,
            "clear_cache": self.clear_cache,
            "echo": self.echo_command,
        }

    async def run(self, query: str, context: Any, user_id: str = "system") -> Dict[str, Any]:
        """
        Executes a structured plan step.

        Expected context format:
        {
            "action": "restart_service",
            "params": {...}
        }
        """
        try:
            if not isinstance(context, dict):
                return {"error": "Invalid context. Expected JSON object with `action` key."}

            action = context.get("action")
            params = context.get("params", {})

            if action not in self.allowed_actions:
                log_event("control_agent_reject", {"user": user_id, "action": action})
                return {"error": f"Action '{action}' is not permitted."}

            result = await self.allowed_actions[action](**params)
            log_event("control_agent_success", {"user": user_id, "action": action, "result": result})

            return {
                "result": result,
                "status": "executed",
                "action": action,
                "params": params,
            }

        except Exception as e:
            log_event("control_agent_error", {"user": user_id, "error": str(e)})
            return {"error": f"Failed to execute action: {str(e)}"}

    # === Safe actions — extend for real ops ===

    async def restart_service(self) -> str:
        """Mocked restart action."""
        # Replace with actual service manager command if needed
        return self._run_command("systemctl restart relay-backend.service")

    async def clear_cache(self) -> str:
        """Mocked cache clear."""
        return self._run_command("rm -rf /tmp/relay_cache/*")

    async def echo_command(self, message: str = "Hello") -> str:
        """Simple echo test."""
        return self._run_command(f"echo {shlex.quote(message)}")

    def _run_command(self, cmd: str) -> str:
        """Runs a shell command and returns output or error."""
        try:
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return f"Command failed: {e.stderr.strip()}"


# === Export instance ===
control_agent = ControlAgent()
