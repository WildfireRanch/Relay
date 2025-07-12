# ---- Use Node.js LTS base (Debian, for compatibility with Playwright/Node tools) ----
FROM node:20-bullseye

# ---- Install Python and pip ----
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    ln -sf python3 /usr/bin/python && \
    pip install --upgrade pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ---- Set working directory ----
WORKDIR /app

# ---- Copy only requirements first for layer caching ----
COPY requirements.txt .

# ---- Install Python dependencies ----
RUN pip install --no-cache-dir -r requirements.txt

# ---- Copy all app code ----
COPY . .

# ---- Install Node dependencies for your JS scraper ----
RUN if [ -f backend/solark_browser/package.json ]; then \
      npm install --prefix backend/solark_browser; \
    fi

# ---- (Optional) Install Playwright browser binaries if your scraper uses Playwright (JS or Python) ----
# If you use Playwright in Python:
RUN if grep -q 'playwright' requirements.txt; then \
      playwright install --with-deps; \
    fi

# If you use Playwright in Node:
RUN if [ -f backend/solark_browser/package.json ]; then \
      npx playwright install --with-deps --cwd backend/solark_browser; \
    fi

# ---- Set environment variables for robust Python behavior ----
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ---- Default command: run your SolArk cron job ----
CMD bash -lc "cd backend/solark_browser && node fetch_plant_flow.js && python3 poll_and_insert.py"
