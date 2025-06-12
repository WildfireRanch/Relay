# Use official slim Python 3.11 image for smaller size and speed
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy only requirements first for Docker layer caching (faster rebuilds if only code changes)
COPY requirements.txt .

# Install pip dependencies first to leverage cache
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose default FastAPI port (optional, for local/dev use)
EXPOSE 8000

# Set environment variables for Python (good for async apps)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Start with uvicorn (production best practice for FastAPI); adjust if you want python main.py instead
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
# If you must run as a script instead, uncomment the line below and comment the above
# CMD ["python", "main.py"]
