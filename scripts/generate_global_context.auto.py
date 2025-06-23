# File: scripts/generate_global_context_auto.py
# Purpose: Auto-generate /docs/generated/global_context.auto.md from all /context/*.md

from pathlib import Path
from datetime import datetime

CONTEXT_DIR = Path("./context")
OUTPUT_FILE = Path("./docs/generated/global_context.auto.md")

HEADER = f"""# Auto-Generated Global Context

_Last updated: {datetime.utcnow().isoformat()}Z_
"""

sections = []
for md_file in sorted(CONTEXT_DIR.glob("*.md")):
    title = md_file.stem.replace("_", " ").title()
    body = md_file.read_text()
    sections.append(f"\n## {title}\n\n{body.strip()}\n")

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE.write_text(HEADER + "\n".join(sections))
print(f"✅ Generated: {OUTPUT_FILE.relative_to(Path.cwd())}")
