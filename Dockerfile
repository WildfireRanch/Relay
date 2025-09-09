# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile – Relay (FastAPI)
# - Uses Python 3.11 slim
# - Installs deps with caching
# - Runs as non-root
# - Binds to ${PORT} (Railway will inject it)
# - Adds HTTP healthcheck hitting "/"
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# (Optional) curl for HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m appuser

WORKDIR /app

# Layer cache: deps first
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Informational (Railway ignores EXPOSE; we still include for local run)
EXPOSE 8000

# Runtime env
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Healthcheck (adjust path if you have /health)
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/" || exit 1

# Drop privileges
USER appuser

# IMPORTANT: use shell so ${PORT} expands
# (Switch to gunicorn variant if you prefer)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]

# Alternative:
# CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:${PORT} main:app"]
