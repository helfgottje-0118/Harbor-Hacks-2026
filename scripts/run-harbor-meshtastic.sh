#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env.mesh ]]; then
  set -a
  source .env.mesh
  set +a
fi
: "${HARBOR_API_URL:?Set HARBOR_API_URL in .env.mesh}"
: "${HARBOR_MESH_GATEWAY_TOKEN:?Set HARBOR_MESH_GATEWAY_TOKEN in .env.mesh}"
: "${MESHTASTIC_PORT:?Set MESHTASTIC_PORT in .env.mesh}"
exec python3 scripts/harbor_meshtastic_bridge.py
