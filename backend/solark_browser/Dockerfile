# --- Use Node.js LTS base (Debian for maximum compatibility) ---
FROM node:20-bullseye

# --- Install Python 3 and pip ---
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    ln -sf python3 /usr/bin/python && \
    pip install --upgrade pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Set working directory ---
WORKDIR /app

# --- Copy only requirements first for Docker cache efficiency ---
COPY requirements.txt .

# --- Install Python dependencies (add Playwright if needed) ---
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps

# --- Copy in app code (worker scripts, package.json, etc) ---
COPY . .

# --- Install Node dependencies if package.json exists (for JS script) ---
RUN if [ -f package.json ]; then npm install; fi

# --- Install Playwright browsers for JS, if package.json exists and Playwright is a dep ---
RUN if [ -f package.json ] && grep -q 'playwright' package.json; then npx playwright install --with-deps; fi

# --- Set recommended Python environment variables ---
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- CMD: runs all scripts in order ---
# 1. node fetch_token.js         => fetches token from SolArk and writes auth_token.txt
# 2. node fetch_plant_flow.js    => uses the token to get plant data and writes plant_flow.json
# 3. python3 poll_and_insert.py  => loads data into your database
CMD bash -lc "node fetch_token.js && node fetch_plant_flow.js && python3 poll_and_insert.py"
