#!/bin/bash
# Test script to verify Ask pipeline fix

echo "🔍 Testing Ask Pipeline Fix"
echo "=============================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test 1: Check environment variables
echo "1️⃣ Checking environment variables..."
if grep -q "RELAY_API_KEY" /workspaces/Relay/.env 2>/dev/null; then
    echo -e "${GREEN}✓${NC} RELAY_API_KEY found in .env"
else
    echo -e "${RED}✗${NC} RELAY_API_KEY missing from .env"
fi

if grep -q "NEXT_PUBLIC_API_URL" /workspaces/Relay/.env 2>/dev/null; then
    echo -e "${GREEN}✓${NC} NEXT_PUBLIC_API_URL found in .env"
else
    echo -e "${RED}✗${NC} NEXT_PUBLIC_API_URL missing from .env"
fi

echo ""

# Test 2: Check if frontend uses proxy
echo "2️⃣ Checking AskAgent component..."
if grep -q '"/api/ask/run"' /workspaces/Relay/frontend/src/components/ui/AskAgent/AskAgent.tsx; then
    echo -e "${GREEN}✓${NC} AskAgent uses Next.js API proxy"
else
    echo -e "${RED}✗${NC} AskAgent NOT using proxy (still has direct backend call)"
fi

if grep -q 'relay.wildfireranch.us/ask' /workspaces/Relay/frontend/src/components/ui/AskAgent/AskAgent.tsx; then
    echo -e "${RED}✗${NC} AskAgent still has hardcoded backend URL"
else
    echo -e "${GREEN}✓${NC} No hardcoded backend URLs"
fi

echo ""

# Test 3: Check API proxy route exists
echo "3️⃣ Checking API proxy route..."
if [ -f "/workspaces/Relay/frontend/src/app/api/ask/run/route.ts" ]; then
    echo -e "${GREEN}✓${NC} API proxy route exists"
else
    echo -e "${RED}✗${NC} API proxy route missing"
fi

echo ""

# Test 4: Check backend is accessible
echo "4️⃣ Testing backend connectivity..."
BACKEND_URL=$(grep NEXT_PUBLIC_API_URL /workspaces/Relay/.env | cut -d= -f2)
if [ -n "$BACKEND_URL" ]; then
    if curl -s -f "$BACKEND_URL/livez" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Backend is accessible at $BACKEND_URL"
    else
        echo -e "${RED}✗${NC} Backend not accessible at $BACKEND_URL"
    fi
else
    echo -e "${RED}✗${NC} NEXT_PUBLIC_API_URL not set"
fi

echo ""
echo "=============================="
echo "✅ Test complete!"
echo ""
echo "Next steps:"
echo "  1. Rebuild frontend: cd frontend && npm run build"
echo "  2. Start frontend: cd frontend && npm run dev"
echo "  3. Test in browser: http://localhost:3000"
