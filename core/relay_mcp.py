# File: relay_mcp.py
# Directory: core/
# Purpose: Registers core agents as MCP tools using FastAPIMCP

from fastapi import FastAPI, APIRouter, Request
from fastapi_mcp import FastAPIMCP, tool
from typing import Optional
from agents import codex_agent
from agents.mcp_agent import run_mcp  # ✅ Move this import to the top

mcp = FastAPIMCP()
router = APIRouter(prefix="/mcp", tags=["mcp"])

@tool(
    name="codex.generate_patch",
    description="Generate a code patch from a natural language prompt and optional source code.",
    input_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "code": {"type": "string"}
        },
        "required": ["prompt"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "patch": {"type": "string"}
        }
    }
)
async def codex_generate_patch(prompt: str, code: Optional[str] = "") -> dict:
    context = code or ""
    result = await codex_agent.handle(user_id="mcp-user", query=prompt, context=context)
    return {"patch": result.get("response", "(no response)")}


# === Register with your main FastAPI app ===
def register_mcp(app: FastAPI):
    mcp.mount(app)
    app.include_router(router)


# === Optional test route to trigger tool directly ===
@router.post("/test_tool")
async def test_tool(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "Add logging to the function")
    code = data.get("code", "def handler():\n    pass")
    return await codex_generate_patch(prompt, code)


# ✅ New full Relay run (Codex → Critics → TrainerAgent → Neo4j)
@router.post("/test_run")
async def test_full_mcp_run(request: Request):
    """
    Full MCP test route:
    - Injects context
    - Runs Codex agent
    - Evaluates with critics
    - Logs to TrainerAgent with graph memory
    """
    data = await request.json()
    prompt = data.get("prompt", "Improve the clarity of this function")
    code = data.get("code", "def process(data):\n    return x")

    return await run_mcp(
        query=prompt,
        files=[],
        topics=[],
        role="codex",
        user_id="mcp-test",
        debug=True
    )
