# File: build_index.py
# Purpose: Manual trigger for semantic KB (LlamaIndex) reindex/build from CLI
# Usage: python build_index.py

from services.kb import embed_all

if __name__ == "__main__":
    embed_all()
    print("Index built successfully.")

