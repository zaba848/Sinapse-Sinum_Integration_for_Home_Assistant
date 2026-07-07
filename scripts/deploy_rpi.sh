#!/usr/bin/env bash
# Deploy Sinum integration to Home Assistant on Raspberry Pi.
# Usage:
#   export SINUM_SSH_PASS="<password>"
#   export HA_HOST="10.0.63.53"   # optional; default homeassistant.local
#   export HA_TOKEN="<long-lived-token>"  # optional; triggers restart
#   bash scripts/deploy_rpi.sh

set -euo pipefail

HA_HOST="${HA_HOST:-homeassistant.local}"
HA_USER="${HA_USER:-tomasz}"
HA_TOKEN="${HA_TOKEN:-}"
REMOTE_PARENT="/config/custom_components"
REMOTE_DIR="${REMOTE_PARENT}/sinum"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_PARENT="${REPO_ROOT}/custom_components"

if [ -z "${SINUM_SSH_PASS:-}" ]; then
  echo "ERROR: SINUM_SSH_PASS environment variable not set." >&2
  exit 1
fi

export SSHPASS="$SINUM_SSH_PASS"
SSH=(
  sshpass -e ssh
  -o StrictHostKeyChecking=no
  -o PubkeyAuthentication=no
  "${HA_USER}@${HA_HOST}"
)

echo "==> Deploying custom_components/sinum to ${HA_USER}@${HA_HOST} (single tar session)..."
tar czf - -C "${SRC_PARENT}" sinum | "${SSH[@]}" "mkdir -p ${REMOTE_PARENT} && tar xzf - -C ${REMOTE_PARENT}"

echo "==> Remote manifest version:"
"${SSH[@]}" "python3 -c \"import json; print(json.load(open('${REMOTE_DIR}/manifest.json'))['version'])\""

echo "==> Restarting Home Assistant..."
if [ -n "$HA_TOKEN" ]; then
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://${HA_HOST}:8123/api/services/homeassistant/restart" \
    -H "Authorization: Bearer ${HA_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{}")
  if [ "$http_code" = "200" ] || [ "$http_code" = "504" ]; then
    echo "  HA restart triggered (HTTP ${http_code})."
  else
    echo "  HA restart returned HTTP ${http_code} — restart manually if needed."
  fi
else
  echo "  HA_TOKEN not set — restart HA manually."
fi

echo "==> Done. Monitor HA logs for integration load."
