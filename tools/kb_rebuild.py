# ──────────────────────────────────────────────────────────────────────────────
# File: tools/kb_rebuild.py
# Purpose: Thin CLI wrapper to (re)build the KB and print status to stdout/stderr
# Usage:
#   python tools/kb_rebuild.py --verbose
#   python tools/kb_rebuild.py --root /workspace/Relay --verbose
#   python -m tools.kb_rebuild --health
# Env:
#   KB_EMBED_MODEL / OPENAI_EMBED_MODEL
#   WIPE_INDEX=1 (optional) to force a clean build
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations
import argparse
import os
import sys

def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild the Relay KB index.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--root", default=None, help="Project root (sets RELAY_PROJECT_ROOT)")
    parser.add_argument("--health", action="store_true", help="Non-destructive KB health probe")
    args = parser.parse_args()

    if args.root:
        os.environ["RELAY_PROJECT_ROOT"] = args.root

    try:
        from services import kb
    except Exception as e:
        print(f"[kb_rebuild] failed to import services.kb: {e}", file=sys.stderr)
        return 2

    if args.health:
        # Reuse module CLI health
        return kb._cli(["health"])

    status = kb.embed_all(verbose=args.verbose)
    if status.get("ok"):
        print(f"[kb_rebuild] OK — model={status.get('model')} docs={status.get('indexed')}")
        return 0
    else:
        print(f"[kb_rebuild] ERROR — {status.get('error')}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
