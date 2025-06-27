# File: agents/codex_agent.py
# Purpose: Handle code-editing tasks like bugfixes, refactors, or docstring generation
# Usage: Called by /ask or other routes when a code patch is requested
# Response includes a natural language summary and a structured "patch" action
# Dependencies: OpenAI (GPT-4), Relay config, project file context

import os
from typing import Dict, Any, Optional

from openai import AsyncOpenAI, OpenAIError
from utils.patch_utils import validate_patch_format  # TODO: Implement this helper
from core.logging import log_event  # Centralized Relay logging
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# === CodexAgent Main Handler ===
async def handle(message: str, context: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Handles natural language prompts to perform code editing tasks.

    Args:
        message (str): Natural language request like "Fix this bug".
        context (str): Relevant file or code snippet text.
        user_id (str, optional): For logging or multi-tenant use.

    Returns:
        Dict with:
            - response: natural language summary of change
            - action: { type: "patch", target_file, patch, reason }
    """
    if not message or not context:
        raise ValueError("Both message and context must be provided.")

    prompt = build_prompt(message, context)

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a senior software engineer generating code patches from user requests."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
    except OpenAIError as e:
        log_event("codex_agent_error", {"error": str(e), "user_id": user_id})
        raise RuntimeError("Codex agent failed to respond.") from e

    content = completion.choices[0].message.content.strip()

    # TODO: Replace this with proper YAML/JSON extraction once structured output is enforced
    response, action = parse_codex_response(content)

    if not validate_patch_format(action):
        raise ValueError("Invalid patch format returned from Codex.")

    log_event("codex_agent_success", {"action": action, "user_id": user_id})

    return {
        "response": response,
        "action": action
    }


# === Prompt Builder ===
def build_prompt(message: str, context: str) -> str:
    return f"""
You will receive a code editing request from a user, along with the relevant code context.

Task: {message}

Code Context:
```python
{context}
```

Please return:
1. A brief natural language summary of the change
2. A code patch (diff-style or full replacement), targeting a specific file
3. A short reason explaining why the patch is needed

Output format:
```
Summary: <text>
File: <relative/path/to/file.py>
Patch:
<diff or full replacement>
Reason: <text>
```
"""


# === Response Parser ===
def parse_codex_response(content: str) -> (str, Dict[str, str]):
    # Simple heuristic parser — replace with structured extraction later
    lines = content.strip().splitlines()
    summary = next((line.replace("Summary:", "").strip() for line in lines if line.startswith("Summary:")), "Edit generated.")
    file_line = next((line for line in lines if line.startswith("File:")), "")
    file_path = file_line.replace("File:", "").strip()

    patch_lines = []
    reason = "No reason provided."
    in_patch = False

    for line in lines:
        if line.startswith("Patch:"):
            in_patch = True
            continue
        if line.startswith("Reason:"):
            reason = line.replace("Reason:", "").strip()
            break
        if in_patch:
            patch_lines.append(line)

    return summary, {
        "type": "patch",
        "target_file": file_path,
        "patch": "\n".join(patch_lines).strip(),
        "reason": reason
    }


# === TODOs for Future ===
# - Validate patch syntax or apply dry-run (AST-based)
# - Add preview rendering endpoint (/preview/patch)
# - Allow multi-file actions (currently only supports 1 file)
# - Add agent self-critique / fallback suggestion
