#!/usr/bin/env bash
# Deploy Sinum integration to Home Assistant via SSH
# Usage: ./deploy_to_ha.sh [ha_ip] [ssh_port]
# Default: ha_ip=10.0.63.53, ssh_port=22
set -e

HA_IP="${1:-10.0.63.53}"
SSH_PORT="${2:-22}"
HA_USER="root"
REMOTE_DIR="/config/custom_components/sinum"
LOCAL_DIR="$(dirname "$0")/custom_components/sinum"

echo "Deploying Sinum integration to $HA_IP:$SSH_PORT..."
echo "Source: $LOCAL_DIR"
echo "Target: $HA_USER@$HA_IP:$REMOTE_DIR"
echo ""

# Create target directory on HA
ssh -p "$SSH_PORT" "$HA_USER@$HA_IP" "mkdir -p $REMOTE_DIR"

# Copy all integration files
scp -P "$SSH_PORT" -r "$LOCAL_DIR"/* "$HA_USER@$HA_IP:$REMOTE_DIR/"

echo ""
echo "Files deployed. Restarting Home Assistant..."
ssh -p "$SSH_PORT" "$HA_USER@$HA_IP" "ha core restart"

echo ""
echo "Done! HA is restarting. Wait ~60s then add the integration:"
echo "  Settings -> Devices & Services -> Add Integration -> Sinum"
echo "  Hub IP: 10.0.61.220"
