#!/usr/bin/env bash
# Deploy Sinum integration to Home Assistant via SSH.
#
# Usage:
#   ./deploy_to_ha.sh <ha_ip> [ssh_port]
#
# Example:
#   ./deploy_to_ha.sh 192.168.1.50
#   ./deploy_to_ha.sh 192.168.1.50 22222

set -e

HA_IP="${1:?Usage: ./deploy_to_ha.sh <ha_ip> [ssh_port]}"
SSH_PORT="${2:-22}"
HA_USER="root"
REMOTE_DIR="/config/custom_components/sinum"
LOCAL_DIR="$(dirname "$0")/custom_components/sinum"

echo "Deploying Sinum integration to $HA_IP:$SSH_PORT ..."
echo "Source : $LOCAL_DIR"
echo "Target : $HA_USER@$HA_IP:$REMOTE_DIR"
echo ""

ssh -p "$SSH_PORT" "$HA_USER@$HA_IP" "mkdir -p $REMOTE_DIR"
scp -P "$SSH_PORT" -r "$LOCAL_DIR"/* "$HA_USER@$HA_IP:$REMOTE_DIR/"

echo ""
echo "Files deployed. Restart Home Assistant from the UI or run:"
echo "  ssh -p $SSH_PORT $HA_USER@$HA_IP 'ha core restart'"
