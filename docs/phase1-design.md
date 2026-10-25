# HARBOR Phase 1 Design

## Repository directory structure

```text
/root/harbor/
├── backend/
│   └── app/
│       ├── __init__.py
│       ├── database.py
│       ├── main.py
│       └── models.py
├── docs/
│   └── phase1-design.md
├── tests/
│   ├── conftest.py
│   └── test_phase1_backend.py
├── README.md
├── requirements.txt
└── .gitignore
```

## System architecture

Phase 1 establishes the local backend foundation:

Phone / local client → FastAPI app → SQLAlchemy ORM → local SQLite database.

The backend is designed to run entirely on the local machine and expose local HTTP endpoints over LAN later. No cloud service, external database, hosted JavaScript, or internet AI dependency is required for Phase 1 runtime.

## Database schema

Phase 1 creates the core HARBOR tables required by the specification:

- `incidents`
- `resources`
- `tasks`
- `nodes`
- `agent_events`

The schema includes the fields listed in the uploaded HARBOR specification. Later phases will add API behavior around these models.

## API design

Phase 1 API endpoints:

- `GET /health` — minimal backend health check.
- `GET /api/system/status` — local system status showing backend, database, Ollama placeholder, LoRa placeholder, and internet placeholder state.

Later phases will add incident, resource, task, node, mesh, and AI endpoints.

## Implementation sequence

1. Create repository layout.
2. Create virtual environment and install FastAPI, Uvicorn, SQLAlchemy, Pydantic, pytest, and HTTPX.
3. Write tests for health, status, and SQLite table creation.
4. Verify tests fail before production implementation.
5. Implement SQLAlchemy database connection and models.
6. Implement FastAPI app and startup table creation.
7. Run tests until passing.
8. Run Uvicorn and verify endpoints over HTTP on port 8010 when port 8000 is already occupied.
