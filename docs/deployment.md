# Relay Command Center - Deployment Guide

This document covers the complete deployment process for the Relay Command Center, including Railway (backend) and Vercel (frontend) deployments.

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   External      │
│   (Vercel)      │    │   (Railway)     │    │   Services      │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • Next.js App   │◄──►│ • FastAPI       │◄──►│ • OpenAI API    │
│ • Static Files  │    │ • Agent System  │    │ • Google Docs   │
│ • API Proxies   │    │ • KB/Search     │    │ • Redis Cache   │
│ • Admin UI      │    │ • Health Checks │    │ • PostgreSQL    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Prerequisites

### Required Tools
- [Railway CLI](https://docs.railway.app/develop/cli) for backend deployment
- [Vercel CLI](https://vercel.com/docs/cli) for frontend deployment
- [Git](https://git-scm.com/) for version control
- [Node.js 18+](https://nodejs.org/) for local development
- [Python 3.11+](https://python.org/) for backend development

### Required Accounts
- [Railway](https://railway.app/) account for backend hosting
- [Vercel](https://vercel.com/) account for frontend hosting
- [OpenAI](https://openai.com/) account for AI services
- [Google Cloud](https://cloud.google.com/) account (optional, for docs sync)

## Environment Setup

### 1. Clone and Setup Repository

```bash
# Clone the repository
git clone https://github.com/yourusername/relay-command-center.git
cd relay-command-center

# Install dependencies
npm install
cd frontend && npm install && cd ..

# Copy environment template
cp .env.example .env
```

### 2. Configure Environment Variables

Edit `.env` with your actual values:

```bash
# Core Authentication
API_KEY=your-secure-api-key
OPENAI_API_KEY=sk-your-openai-key

# Frontend Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000  # Update for production
FRONTEND_ORIGINS=http://localhost:3000     # Update for production

# Optional: Google Docs Integration
GOOGLE_CREDS_JSON=base64-encoded-credentials
GOOGLE_TOKEN_JSON=base64-encoded-token
```

## Railway Deployment (Backend)

### 1. Initial Setup

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Create new project
railway new relay-backend

# Link to existing project (if already created)
railway link [project-id]
```

### 2. Configure Railway Environment

Set environment variables in Railway dashboard or via CLI:

```bash
# Core variables
railway variables set API_KEY=your-secure-api-key
railway variables set OPENAI_API_KEY=sk-your-openai-key
railway variables set ENV=production

# Frontend CORS
railway variables set FRONTEND_ORIGINS=https://your-frontend-domain.vercel.app
railway variables set FRONTEND_ORIGIN_REGEX="^https://([a-z0-9-]+\.)?yourdomain\.com$"

# Optional: Google integration
railway variables set GOOGLE_CREDS_JSON=base64-encoded-credentials
railway variables set GOOGLE_TOKEN_JSON=base64-encoded-token

# Database (if using Railway's PostgreSQL)
railway variables set DATABASE_URL=${{ PostgreSQL.DATABASE_URL }}
```

### 3. Deploy to Railway

```bash
# Deploy current branch
railway up

# Deploy specific service (if using multiple services)
railway up --service backend

# Monitor deployment
railway logs
```

### 4. Custom Domain (Optional)

1. Go to Railway dashboard → Settings → Domains
2. Add your custom domain: `api.yourdomain.com`
3. Configure DNS records as shown
4. Update `NEXT_PUBLIC_API_URL` in Vercel to use custom domain

## Vercel Deployment (Frontend)

### 1. Initial Setup

```bash
# Install Vercel CLI
npm install -g vercel

# Login to Vercel
vercel login

# Link project (run from frontend directory)
cd frontend
vercel link
```

### 2. Configure Vercel Environment Variables

In Vercel dashboard or via CLI:

```bash
# API Configuration
vercel env add NEXT_PUBLIC_API_URL production
# Enter: https://your-railway-app.railway.app (or custom domain)

vercel env add ADMIN_API_KEY production
# Enter: your-secure-api-key

vercel env add ADMIN_UI_TOKEN production
# Enter: secure-admin-token

vercel env add ADMIN_IPS production
# Enter: 203.0.113.10,198.51.100.25 (optional IP allowlist)
```

### 3. Deploy to Vercel

```bash
# Deploy from frontend directory
cd frontend
vercel --prod

# Or deploy via Git integration (recommended)
git push origin main  # If connected to Git
```

### 4. Custom Domain (Optional)

1. Go to Vercel dashboard → Project → Settings → Domains
2. Add your custom domain: `app.yourdomain.com`
3. Configure DNS records as shown
4. Update `FRONTEND_ORIGINS` in Railway to include new domain

## Production Configuration

### Security Headers

The `vercel.json` includes security headers:
- HSTS (Strict Transport Security)
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy restrictions

### Health Checks

Backend provides health endpoints:
- `/livez` - Liveness probe (basic health)
- `/readyz` - Readiness probe (dependencies check)

Configure Railway health checks:
```toml
# railway.toml
[deploy]
healthcheckPath = "/livez"
healthcheckTimeout = 300
```

### CORS Configuration

Ensure CORS is properly configured:

```bash
# Railway Backend
FRONTEND_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
FRONTEND_ORIGIN_REGEX=^https://([a-z0-9-]+\.)?yourdomain\.com$

# Vercel Frontend
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

## Monitoring & Maintenance

### Logs Access

```bash
# Railway logs
railway logs --tail

# Vercel logs
vercel logs your-deployment-url
```

### Health Monitoring

Monitor these endpoints:
- Backend: `GET https://api.yourdomain.com/readyz`
- Frontend: `GET https://app.yourdomain.com` (should return 200)

### Database Backups

If using Railway PostgreSQL:
1. Go to Railway dashboard → Database → Backups
2. Configure automatic backups
3. Test restore procedure

## Troubleshooting

### Common Issues

#### CORS Errors
- Verify `FRONTEND_ORIGINS` in Railway matches Vercel domain
- Check `NEXT_PUBLIC_API_URL` in Vercel points to Railway
- Ensure both HTTP and HTTPS origins if needed

#### Authentication Failures
- Verify `API_KEY` matches between Railway and Vercel
- Check `ADMIN_UI_TOKEN` for admin routes
- Validate IP allowlist if using `ADMIN_IPS`

#### Build Failures

Railway:
```bash
# Check build logs
railway logs

# Verify Dockerfile and requirements.txt
railway shell
```

Vercel:
```bash
# Check build logs in dashboard
vercel logs

# Test build locally
cd frontend && npm run build
```

#### Environment Variable Issues
- Use `railway variables` to list all variables
- Use `vercel env ls` to check Vercel variables
- Ensure sensitive values are properly base64 encoded

### Performance Optimization

#### Railway
- Monitor CPU/memory usage in dashboard
- Scale up if needed: Railway → Settings → Resources
- Consider Railway's autoscaling features

#### Vercel
- Monitor function execution times
- Optimize bundle size: `npm run build && npx @next/bundle-analyzer`
- Use Vercel Analytics for performance insights

## Rollback Procedures

### Railway Rollback
```bash
# List recent deployments
railway deployments

# Rollback to specific deployment
railway redeploy [deployment-id]
```

### Vercel Rollback
```bash
# List deployments
vercel ls

# Promote previous deployment
vercel promote [deployment-url]
```

### Database Rollback
If using Railway PostgreSQL:
1. Stop the application
2. Restore from backup in Railway dashboard
3. Restart application
4. Verify data integrity

## CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: railway/cli@v2
        with:
          railway-token: ${{ secrets.RAILWAY_TOKEN }}
      - run: railway up --service backend

  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: amondnet/vercel-action@v20
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          working-directory: ./frontend
```

## Support & Resources

- [Railway Documentation](https://docs.railway.app/)
- [Vercel Documentation](https://vercel.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)

For project-specific issues, refer to the main [README.md](../README.md) or create an issue in the repository.