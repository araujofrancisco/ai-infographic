#!/usr/bin/env bash
set -euo pipefail

# Detect Docker gateway IP from the default route
GATEWAY_IP=$(ip route | awk '/default via/ {print $3; exit}')

if [ -z "$GATEWAY_IP" ]; then
    echo "⚠️  Could not detect Docker gateway IP"
    exit 1
fi

echo "🔍 Detected Docker gateway IP: $GATEWAY_IP"

# Export the variable for subprocesses (uvicorn / the app)
export OLLAMA_URL="http://${GATEWAY_IP}:11434"
echo "🔧 Exported OLLAMA_URL=http://${GATEWAY_IP}:11434"
