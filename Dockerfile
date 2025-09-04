# Use official slim Python 3.11 image for smaller size and speed
FROM python:3.11-slim

# System deps (optional: curl for HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m appuser

# Set working directory
WORKDIR /app

# Copy only requirements first for Docker layer caching (faster rebuilds if only code changes)
COPY requirements.txt .

# Install pip dependencies first to leverage cache
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose default FastAPI port (informational)
EXPOSE 8000

# Environment for Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Healthcheck (expects your root path to return 200)
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/" || exit 1

# Drop privileges
USER appuser

# Use shell form so ${PORT} expands at runtime
# Gunicorn is more production-friendly, uses uvicorn workers under the hood
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:${PORT} main:app"]
