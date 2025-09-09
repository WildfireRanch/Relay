# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile – Relay (FastAPI)
# Python 3.11 slim, non-root, healthcheck, proper perms for logs/docs/index
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

# Ensure writable app dirs (fixes logs router permission warnings)
RUN mkdir -p /app/logs /app/docs/imported /app/docs/generated /app/data/index \
 && chown -R appuser:appuser /app

# Informational (Railway ignores EXPOSE; still useful locally)
EXPOSE 8000

# Runtime env
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    ENV=production \
    PORT=8000

# Healthcheck (cheaper liveness path)
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/live" || exit 1

# Drop privileges
USER appuser

# IMPORTANT: use shell so ${PORT} expands
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]

# Alternative (Gunicorn):
# CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:${PORT} main:app"]
