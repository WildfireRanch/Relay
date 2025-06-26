import os
from pathlib import Path

# Use current working directory as fallback
DEFAULT_PROJECT_ROOT = Path.cwd()

ENV_NAME = os.getenv("ENV", "dev")
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)

# Safer defaults: allow override, but don't break in test/dev
INDEX_ROOT = Path(os.getenv("INDEX_ROOT", str(DEFAULT_PROJECT_ROOT / "index" / ENV_NAME)))
INDEX_DIR = Path(os.getenv("INDEX_DIR", str(INDEX_ROOT / MODEL_NAME)))

INDEX_DIR.mkdir(parents=True, exist_ok=True)
