from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.app.database import Base, engine, init_db
from backend.app.main import app
from backend.app import models


def test_root_endpoint_shows_harbor_landing_page():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "HARBOR" in response.text
    assert "OFFLINE EMERGENCY COMMAND" in response.text
    assert "Emergency Ops Console" in response.text
    assert 'id="root"' in response.text


def test_health_endpoint_reports_backend_alive():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "harbor-backend"}


def test_system_status_endpoint_reports_local_components():
    client = TestClient(app)

    response = client.get("/api/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "ONLINE"
    assert payload["database"] == "ONLINE"
    assert payload["ollama"] in {"UNKNOWN", "ONLINE", "OFFLINE"}
    assert payload["lora"] == "SIMULATION_READY"
    assert payload["internet"] in {"UNKNOWN", "ONLINE", "OFFLINE"}


def test_init_db_creates_required_harbor_tables():
    init_db()

    table_names = set(inspect(engine).get_table_names())

    assert {
        "incidents",
        "resources",
        "tasks",
        "nodes",
        "agent_events",
    }.issubset(table_names)


def test_incident_model_contains_phase1_required_columns():
    columns = {column.name for column in models.Incident.__table__.columns}

    assert {
        "id",
        "timestamp",
        "source",
        "node_id",
        "latitude",
        "longitude",
        "category",
        "description",
        "severity",
        "people_affected",
        "status",
        "ai_reasoning",
        "recommended_action",
    }.issubset(columns)
