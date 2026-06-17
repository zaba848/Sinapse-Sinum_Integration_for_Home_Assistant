#!/bin/bash
# Verify connection to Sinum hub and show mqtt_bridge.lua upload instructions.
#
# Usage:
#   export SINUM_HUB_URL=http://192.168.1.100
#   export SINUM_API_TOKEN=<your-api-token>
#   ./deploy_lua_to_hub.sh
#
# Or pass as arguments:
#   ./deploy_lua_to_hub.sh http://192.168.1.100 <token>

set -e

HUB_URL="${SINUM_HUB_URL:-${1:?Usage: SINUM_HUB_URL=http://hub-ip ./deploy_lua_to_hub.sh}}"
API_TOKEN="${SINUM_API_TOKEN:-${2:?Usage: SINUM_API_TOKEN=<token> ./deploy_lua_to_hub.sh}}"

echo "Verifying connection to $HUB_URL ..."

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  "$HUB_URL/api/v1/info" \
  -H "Authorization: Bearer $API_TOKEN")

if [ "$HTTP_CODE" != "200" ]; then
  echo "ERROR: Hub returned HTTP $HTTP_CODE. Check URL and token."
  exit 1
fi

echo "Connected. Upload mqtt_bridge.lua manually:"
echo ""
echo "  1. Open $HUB_URL in a browser"
echo "  2. Settings -> Lua Scripts -> New Script"
echo "  3. Paste the contents of: lua_scripts/mqtt_bridge.lua"
echo "     File size: $(wc -c < lua_scripts/mqtt_bridge.lua) bytes"
echo "  4. Set CLIENT_ID = 1  (adjust if you have multiple HA instances)"
echo "  5. Save and Enable"
echo "  6. Check hub logs for: [Sinapse] MQTT bridge started"
