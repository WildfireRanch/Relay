"""
Lightweight package marker for internal utils.

Ensures `from utils import ...` imports resolve when the app is run
from various working directories (e.g., uvicorn, gunicorn, pytest).
"""

