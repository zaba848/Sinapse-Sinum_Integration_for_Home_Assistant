#!/bin/bash
# Deploy Lua scripts to Sinum hub via API
# Usage: ./deploy_lua_to_hub.sh

set -e

HUB_URL="http://10.0.61.220"
API_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3NfdXVpZCI6IjNmOTlmNGE5LTYxM2YtNDBiNy1iOTAzLWU0Mzk3MWE5MzFhZSIsImV4cGlyZXNfYXQiOjAsImV4cGlyZXNfaW4iOjAsInVzZXJfaWQiOiIxIiwidXNlcl9uYW1lIjoiUGFuZWtfVGVzdF9Ub2tlbiIsInVzZXJfcm9sZSI6IlJPTEVfQVBJX1RPS0VOIn0.FVD_za2gNB5FlGp88Qsza0pKBBfeD9faj8oKSBncoN8"

echo "=========================================="
echo "🚀 Deploying Lua Scripts to Sinum Hub"
echo "=========================================="
echo "Hub: $HUB_URL"
echo ""

# Read the MQTT bridge script
echo "📄 Reading mqtt_bridge.lua..."
MQTT_BRIDGE=$(cat lua_scripts/mqtt_bridge.lua | jq -Rs .)

# Step 1: Verify connection
echo ""
echo "1️⃣  Verifying hub connection..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
  "$HUB_URL/api/v1/info" \
  -H "Authorization: Bearer $API_TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" != "200" ]; then
  echo "❌ Failed to connect (HTTP $HTTP_CODE)"
  exit 1
fi

echo "✅ Connected to hub"
echo "Response: $(echo "$BODY" | jq -r '.name // "Unknown"')"

echo ""
echo "2️⃣  📝 MQTT BRIDGE UPLOAD"
echo "   Note: Manual upload required via Sinum web UI"
echo "   Settings → Lua Scripts → New Script"
echo "   Copy content from: lua_scripts/mqtt_bridge.lua"
echo "   Set CLIENT_ID = 1 (adjust as needed)"
echo ""
echo "   File size: $(wc -c < lua_scripts/mqtt_bridge.lua) bytes"

echo ""
echo "=========================================="
echo "✅ Deployment guide prepared!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Open http://10.0.61.220 in browser"
echo "2. Settings → Lua Scripts → New Script"
echo "3. Paste mqtt_bridge.lua content"
echo "4. Set CLIENT_ID = 1"
echo "5. Save and Enable"
echo "6. Check logs for: [Sinapse] MQTT bridge v0.7 started"
