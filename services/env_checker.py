# ──────────────────────────────────────────────────────────────────────────────
# File: env_checker.py
# Directory: services
# Purpose: # Purpose: Verify that all required environment variables are defined and correctly set up in the system.
#
# Upstream:
#   - ENV: —
#   - Imports: dotenv, os, pathlib, pprint, re
#
# Downstream:
#   - —
#
# Contents:
#   - check_env_keys()
#   - find_env_keys_in_code()

# ──────────────────────────────────────────────────────────────────────────────

import os
import re
from pathlib import Path
from dotenv import dotenv_values

SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

GETENV_REGEX = re.compile(r"os\.getenv\([\"'](.+?)[\"']\)")

def find_env_keys_in_code(path: Path):
    found = {}
    for file in path.rglob("*.py"):
        matches = GETENV_REGEX.findall(file.read_text(encoding="utf-8"))
        if matches:
            found[file.name] = list(set(matches))
    return found

def check_env_keys():
    code_env_usage = find_env_keys_in_code(SERVICES_DIR)
    used_keys = sorted({k for keys in code_env_usage.values() for k in keys})
    
    # Load .env if available
    env_file_values = dotenv_values(dotenv_path=ENV_FILE)
    env_file_keys = set(env_file_values.keys())
    runtime_env_keys = set(os.environ.keys())

    # Compare
    missing_keys = [k for k in used_keys if k not in env_file_keys and k not in runtime_env_keys]
    unused_env_keys = sorted(env_file_keys - set(used_keys))

    return {
        "used_keys": used_keys,
        "missing_in_env": missing_keys,
        "defined_but_unused": unused_env_keys,
        "used_in_files": code_env_usage,
    }
if __name__ == "__main__":
    from pprint import pprint
    result = check_env_keys()
    pprint(result)
