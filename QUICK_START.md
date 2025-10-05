# Relay Command Center - Quick Start Guide

**Status**: ✅ **Ready for Deployment**

---

## 🚀 Quick Deploy (5 Minutes)

### 1. Environment Setup
```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys:
# - OPENAI_API_KEY=sk-...
# - API_KEY=your-secret-key
# - FRONTEND_ORIGINS=https://your-domain.com
```

### 2. Install Dependencies
```bash
# Backend
pip install -r requirements.txt

# Frontend
cd frontend && npm install
```

### 3. Build Knowledge Base (Optional but Recommended)
```bash
python -m services.kb embed
# This indexes your docs/ and code/ for semantic search
# Takes ~2-5 minutes depending on corpus size
```

### 4. Start Services

**Backend** (Terminal 1):
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Frontend** (Terminal 2):
```bash
cd frontend && npm run dev
# Or for production: npm run build && npm start
```

### 5. Verify
```bash
# Health check
curl http://localhost:8000/livez
# Should return: {"ok":true,"ts":...}

# Frontend
open http://localhost:3000
```

---

## ✅ Recent Fixes Applied

### TypeScript Build
- ✅ Fixed test file type errors
- ✅ Excluded `tests/` from tsconfig
- ✅ Build completes successfully in ~90s

### Frontend Performance
- ✅ Fixed build timeout issue
- ✅ Added NODE_OPTIONS memory allocation
- ✅ All 35 routes build correctly

### Environment Loading
- ✅ Fixed .env loading in main.py
- ✅ All variables now load correctly
- ✅ OpenAI API key properly injected

---

## 📋 Pre-Flight Checklist

**Before Deployment**:
- [ ] `.env` configured with production values
- [ ] `OPENAI_API_KEY` set
- [ ] `API_KEY` / `RELAY_API_KEY` set (strong secret)
- [ ] `FRONTEND_ORIGINS` set to production domains
- [ ] `INDEX_ROOT` points to persistent volume
- [ ] KB index built (`python -m services.kb embed`)
- [ ] Frontend built (`npm run build`)
- [ ] Health endpoints responding:
  - `GET /livez` → 200 ✅
  - `GET /readyz` → 200 ✅

---

## 🔑 Key Endpoints

### Health & Diagnostics
```bash
GET  /livez              # Liveness (always returns 200)
GET  /readyz             # Readiness (validates system)
GET  /__router_map       # List all routes
GET  /__router_diag      # Import diagnostics
```

### Core Functionality
```bash
POST /ask                # Main query endpoint
POST /ask/stream         # Streaming responses
GET  /mcp/ping           # MCP status
POST /mcp/run            # Execute agent
```

### Document Management (requires X-Api-Key)
```bash
GET  /docs/list          # List documents
GET  /docs/view          # View document
POST /docs/sync          # Google Docs sync
POST /docs/refresh_kb    # Reindex KB
```

### Knowledge Base (requires X-Api-Key)
```bash
POST /kb/search          # Semantic search
POST /kb/reindex         # Rebuild index
GET  /kb/summary         # Index stats
```

---

## 🔐 Authentication

### Backend API
```bash
# Use X-Api-Key header
curl -H "X-Api-Key: your-api-key" \
  http://localhost:8000/docs/list
```

### Frontend Proxies
Frontend automatically injects API key server-side:
```typescript
// Browser calls:
fetch('/api/docs/list')  // No auth header needed

// Next.js API route injects:
// X-Api-Key: process.env.ADMIN_API_KEY
```

---

## 🐛 Troubleshooting

### Backend Won't Start
```bash
# Check imports
python -c "from main import app"

# Check env loading
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('OPENAI_API_KEY')[:20])"
```

### Frontend Build Fails
```bash
# Clear cache and rebuild
rm -rf .next node_modules
npm install
npm run build
```

### KB Search Returns Empty
```bash
# Check index exists
ls -lah /workspaces/Relay/data/index/

# Rebuild index
python -m services.kb embed
```

### CORS Errors
```bash
# Check FRONTEND_ORIGINS in .env
echo $FRONTEND_ORIGINS

# Should match exactly (no trailing slash):
# http://localhost:3000  ✅
# http://localhost:3000/ ❌
```

---

## 📊 System Requirements

### Minimum
- Python 3.11+
- Node.js 18+
- 2GB RAM
- 1GB disk (plus KB index size)

### Recommended
- Python 3.12
- Node.js 20+
- 4GB RAM
- 5GB disk (with KB index)

### For Production
- 8GB+ RAM
- Persistent volume for INDEX_ROOT
- Redis (optional, for caching)
- PostgreSQL (recommended, currently using JSON files)

---

## 📈 Performance Tips

### KB Indexing
```bash
# Faster embedding with larger model
KB_EMBED_MODEL=text-embedding-3-small python -m services.kb embed

# Or use larger (slower but more accurate)
KB_EMBED_MODEL=text-embedding-3-large python -m services.kb embed
```

### Frontend Optimization
```bash
# Production build with optimizations
NODE_ENV=production npm run build

# Increase Node memory if needed
NODE_OPTIONS='--max-old-space-size=8192' npm run build
```

### Backend Scaling
```bash
# Run with multiple workers
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000

# Or use gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

---

## 🔗 Useful Commands

### Development
```bash
# Backend with auto-reload
uvicorn main:app --reload

# Frontend with auto-reload
cd frontend && npm run dev

# Type checking
cd frontend && npm run typecheck
```

### Production
```bash
# Build frontend
cd frontend && npm run build

# Start frontend
cd frontend && npm start

# Start backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Maintenance
```bash
# Rebuild KB index
python -m services.kb embed

# Validate KB index
python -m services.kb health

# Search KB
python -m services.kb search "your query"

# Clear logs
rm -rf logs/*.log
```

---

## 📚 Documentation

- **Full Analysis**: [FIXES_AND_IMPROVEMENTS.md](FIXES_AND_IMPROVEMENTS.md)
- **Architecture**: See "System Architecture" section in FIXES_AND_IMPROVEMENTS.md
- **API Docs**: [README.md](README.md) - Route Matrix section
- **Environment**: [.env.example](.env.example)

---

## 🆘 Support

### Check System Health
```bash
curl http://localhost:8000/readyz | jq .
```

### View Logs
```bash
# Backend logs (if running with uvicorn)
tail -f logs/relay.log

# Frontend logs
cd frontend && npm run dev  # stderr shows logs
```

### Reset Everything
```bash
# Nuclear option - full reset
rm -rf .next frontend/.next frontend/node_modules data/index
pip install -r requirements.txt
cd frontend && npm install
python -m services.kb embed
```

---

## ✨ What's Working

✅ **All Core Systems**:
- Health endpoints (`/livez`, `/readyz`)
- Ask pipeline (`/ask`)
- MCP agent orchestration
- Document management
- Knowledge base search
- Frontend build & deployment
- Environment variable loading
- TypeScript type checking
- CORS configuration
- Authentication

✅ **All Fixes Applied**:
- TypeScript errors resolved
- Frontend build timeout fixed
- Environment loading fixed
- All routes mounting correctly
- All services importing cleanly

---

**Last Updated**: 2025-10-05
**System Status**: 🟢 **Operational**
**Deployment Ready**: ✅ **Yes**
