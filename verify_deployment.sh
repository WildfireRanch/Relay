#!/bin/bash
# Verification script for Ask pipeline deployment

echo "🔍 Deployment Verification Checklist"
echo "====================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "✅ COMPLETED FIXES:"
echo "  1. Frontend Ask component uses API proxy"
echo "  2. Tailwind moved to dependencies for Vercel"
echo ""

echo "📋 VERIFICATION STEPS:"
echo ""
echo "1️⃣ Check Vercel Build Status"
echo "   → Visit: https://vercel.com/dashboard"
echo "   → Look for latest deployment of Relay project"
echo "   → Should show: ✅ Building... → ✅ Ready"
echo ""

echo "2️⃣ Test Frontend (after deployment)"
echo "   → Visit your production URL"
echo "   → Navigate to Ask/Echo interface"
echo "   → Submit a test query"
echo "   → Should receive response from backend"
echo ""

echo "3️⃣ Monitor Railway Logs"
echo "   Run: railway logs --tail 50 | grep 'POST /ask'"
echo "   Should see incoming requests when you test"
echo ""

echo "4️⃣ Test End-to-End"
TEST_URL="https://relay.wildfireranch.us"
echo "   Backend URL: $TEST_URL"
echo "   Test command:"
echo "   curl -X POST $TEST_URL/ask \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -H 'X-Api-Key: YOUR_KEY' \\"
echo "     -d '{\"query\":\"What is Relay?\"}'"
echo ""

echo -e "${YELLOW}⏳ NEXT ACTIONS:${NC}"
echo "  1. Wait for Vercel build to complete (~2-3 min)"
echo "  2. Test the Ask interface in browser"
echo "  3. Monitor Railway logs for successful requests"
echo ""
echo -e "${GREEN}✅ All fixes are committed and pushed to main!${NC}"
