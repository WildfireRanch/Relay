# File: __init__.py
# Directory: services/
# Purpose: Marks this as a package for Python imports.
# Expose submodules so `from services import embeddings` works
from . import embeddings as embeddings  # noqa: F401
