# Harbor Hacks 2026 — HARBOR + FORGE + Meshtastic

HARBOR is an emergency-information dashboard for incident reports, operator review, and LoRa/Meshtastic communication with the FORGE AI assistant.

## About

HARBOR was built with FORGE AI and integrates Meshtastic LoRa for incident reporting and operator review. This public repository includes an imported codebase with work from before and during Harbor Hacks 2026; commit publication dates are not necessarily feature creation dates.

## Components

- `backend/` — FastAPI incidents, severity triage, Meshtastic receive API, critical-incident operator review, FORGE adapter
- `frontend/` — React/Vite incident dashboard and offline-map interface
- `scripts/harbor_meshtastic_bridge.py` — Mac/Heltec gateway, LoRa reports, draft + confirm commands, acknowledgments
- `tests/` — automated backend behavior checks
- `docs/` — technical notes

## Development

Backend: install Python dependencies from `requirements.txt`, then launch from the project root:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

Frontend: `cd frontend && npm ci && npm run dev`.

To operate the Meshtastic gateway, configure `HARBOR_API_URL`, `MESHTASTIC_PORT`, and `HARBOR_MESH_GATEWAY_TOKEN` in a **local, untracked environment file**, then run `scripts/run-harbor-meshtastic.sh`. The backend FORGE adapter expects a loopback FORGE service and server-only `FORGE_WEBUI_TOKEN`.

## Safety and limitations

Reports from mesh and web clients are **unverified** until human review. HARBOR's internal critical alerts do **not** notify emergency responders. For an actual emergency, contact emergency services directly. The LoRa demo is not an emergency dispatch service.

## Publication notes

This source export deliberately excludes two setup documents flagged for credential-like strings (`docs/real-meshtastic-mac.md` and `scripts/README-meshtastic.md`) and the original MP3 sound asset. The application may need a replacement sound asset for its alert-audio feature. **No runtime tokens, .env files, or personal credentials should be checked into this public repository.**
