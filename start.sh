#!/usr/bin/env bash
set -euo pipefail
cd /root/harbor
source .venv/bin/activate
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${HARBOR_PORT:-8010}"
