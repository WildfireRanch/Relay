import os
from pathlib import Path

PROJECT_ROOT = Path("/app")
ENV_NAME = os.getenv("ENV", "dev")
MODEL_NAME = (
    os.getenv("KB_EMBED_MODEL")
    or os.getenv("OPENAI_EMBED_MODEL")
    or "text-embedding-3-large"
)
INDEX_ROOT = Path(
    os.getenv("INDEX_ROOT", str(PROJECT_ROOT / "index" / ENV_NAME))
)
INDEX_DIR = Path(os.getenv("INDEX_DIR", str(INDEX_ROOT / MODEL_NAME)))
INDEX_DIR.mkdir(parents=True, exist_ok=True)
