#!/usr/bin/env bash
# Deploy Sinum integration to Home Assistant on Raspberry Pi.
# Usage:
#   export SINUM_SSH_PASS="<password>"
#   bash scripts/deploy_rpi.sh
# Or pass password as first argument (avoid if in shared shell history):
#   SINUM_SSH_PASS=... bash scripts/deploy_rpi.sh

set -euo pipefail

HA_HOST="${HA_HOST:-homeassistant.local}"
HA_USER="${HA_USER:-tomasz}"
HA_TOKEN="${HA_TOKEN:-}"
REMOTE_DIR="/config/custom_components/sinum"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)/custom_components/sinum"

if [ -z "${SINUM_SSH_PASS:-}" ]; then
  echo "ERROR: SINUM_SSH_PASS environment variable not set." >&2
  exit 1
fi

export SSHPASS="$SINUM_SSH_PASS"
SSH="sshpass -e ssh -o StrictHostKeyChecking=no -o PubkeyAuthentication=no ${HA_USER}@${HA_HOST}"
SCP="sshpass -e scp -o StrictHostKeyChecking=no -o PubkeyAuthentication=no"

echo "==> Creating remote directory structure..."
$SSH "mkdir -p ${REMOTE_DIR}/translations"

echo "==> Uploading Python modules and config files..."
for f in "$SRC_DIR"/*.py "$SRC_DIR/manifest.json" "$SRC_DIR/strings.json" "$SRC_DIR/services.yaml"; do
  [ -f "$f" ] || continue
  fname=$(basename "$f")
  cat "$f" | $SSH "cat > ${REMOTE_DIR}/${fname}"
  echo "  uploaded: $fname"
done

echo "==> Uploading translations..."
for f in "$SRC_DIR/translations"/*.json; do
  [ -f "$f" ] || continue
  fname=$(basename "$f")
  cat "$f" | $SSH "cat > ${REMOTE_DIR}/translations/${fname}"
  echo "  uploaded: translations/$fname"
done

echo "==> Restarting Home Assistant..."
if [ -n "$HA_TOKEN" ]; then
  curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://${HA_HOST}:8123/api/services/homeassistant/restart" \
    -H "Authorization: Bearer ${HA_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{}" | grep -q "200" && echo "  HA restart triggered." || echo "  HA restart returned non-200."
else
  echo "  HA_TOKEN not set — restart HA manually."
fi

echo "==> Done. Monitor HA logs for integration load."
