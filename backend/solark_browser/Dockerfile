# ── Base: Node 20 LTS on Debian (bullseye) ────────────────────────────────
FROM node:20-bullseye

# ── Install Python & pip ─────────────────────────────────────────────────
RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    ln -sf python3 /usr/bin/python && \
    pip install --upgrade pip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Working directory ────────────────────────────────────────────────────
WORKDIR /app

# ── Copy Python requirements first for cache efficiency ──────────────────
COPY requirements.txt .

# ── Install Python deps (no Playwright) ──────────────────────────────────
RUN pip install --no-cache-dir -r requirements.txt
# If you add Playwright back later, uncomment the next two lines:
# RUN pip install playwright==1.53.2
# RUN playwright install --with-deps

# ── Copy the rest of the source code ─────────────────────────────────────
COPY . .

# ── Install Node deps if package.json exists ─────────────────────────────
RUN if [ -f package.json ]; then npm install --omit=dev; fi

# ── Optional Playwright browsers for JS *only if* Playwright is in package.json ─
RUN if [ -f package.json ] && grep -q '"playwright"' package.json; \
    then npx playwright install --with-deps; fi

# ── Environment tweaks ───────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ── Default command: fetch token → fetch plant flow → insert to DB ───────
CMD bash -lc "node fetch_token.js && node fetch_plant_flow.js && python3 poll_and_insert.py"
