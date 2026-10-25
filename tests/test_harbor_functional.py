from fastapi.testclient import TestClient

from backend.app.main import app


def test_pwa_files_are_served_from_the_built_frontend():
    client = TestClient(app)
    manifest = client.get('/manifest.webmanifest')
    worker = client.get('/service-worker.js')
    icon = client.get('/harbor-icon.svg')
    assert manifest.status_code == 200
    assert manifest.json()['short_name'] == 'HARBOR'
    assert worker.status_code == 200
    assert 'harbor-shell-v3-main-20261021' in worker.text
    assert icon.status_code == 200
    assert '<svg' in icon.text


def test_create_incident_auto_triages_and_lists():
    client = TestClient(app)

    response = client.post(
        "/api/incidents",
        json={
            "source": "WEB",
            "node_id": "PHONE-1",
            "category": "MEDICAL",
            "description": "Tree blocking East Bay Street with one injured person",
            "people_affected": 1,
            "location": "East Bay Street",
        },
    )

    assert response.status_code == 200
    incident = response.json()
    assert incident["id"] > 0
    assert incident["severity"] in {"CRITICAL", "HIGH"}
    assert "injured" in incident["description"].lower()
    assert incident["recommended_action"]

    list_response = client.get("/api/incidents")
    assert list_response.status_code == 200
    assert any(item["id"] == incident["id"] for item in list_response.json())


def test_incident_location_is_geocoded_when_coordinates_are_missing(monkeypatch):
    client = TestClient(app)

    def fake_geocode(location: str | None, description: str):
        assert location == "1600 Pennsylvania Ave NW, Washington, DC"
        return {
            "location": location,
            "latitude": 38.8977,
            "longitude": -77.0365,
            "display_name": "White House, Washington, DC",
            "street_address": "1600 Pennsylvania Ave NW, Washington, DC",
            "provider": "test",
            "maps_url": "geo:38.8977,-77.0365",
        }

    monkeypatch.setattr("backend.app.main.geocode_text", fake_geocode)

    response = client.post(
        "/api/incidents",
        json={
            "description": "Medical emergency outside the gate",
            "category": "MEDICAL",
            "location": "1600 Pennsylvania Ave NW, Washington, DC",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["latitude"] == 38.8977
    assert payload["longitude"] == -77.0365
    assert "Geocoded location" in payload["ai_reasoning"]


def test_incident_geocodes_66_george_street_from_description_without_internet():
    client = TestClient(app)

    response = client.post(
        "/api/incidents",
        json={
            "description": "66 George Street Charleston power line down",
            "category": "UTILITY",
            "people_affected": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["latitude"] == 32.7840902
    assert payload["longitude"] == -79.9380024
    assert "Geocoded location" in payload["ai_reasoning"]


def test_geocode_endpoint_can_parse_report_text_for_line_street(monkeypatch):
    client = TestClient(app)

    def fake_online(query: str):
        assert "4 line street" in query.lower()
        return {
            "latitude": 32.7973582,
            "longitude": -79.9379599,
            "display_name": "4 Line Street, Charleston, SC",
            "street_address": "4 Line Street, Charleston, SC",
        }

    monkeypatch.setattr("backend.app.geocoding._online_geocode", fake_online)
    monkeypatch.setattr("backend.app.geocoding._load_cache", lambda: {})
    monkeypatch.setattr("backend.app.geocoding._save_cache", lambda cache: None)
    from backend.app import geocoding
    geocoding.geocode_location.cache_clear()

    response = client.get("/api/geocode", params={"location": "Tree blocking 4 line street with one injured person"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["latitude"] == 32.7973582
    assert payload["longitude"] == -79.9379599
    assert payload["street_address"] == "4 Line Street, Charleston, SC"
    assert "cached" in payload["provider"]


def test_geocode_endpoint_resolves_named_place_to_street_address():
    client = TestClient(app)

    response = client.get("/api/geocode", params={"location": "Tree blocking Charleston School of Law"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["street_address"] == "385 Meeting Street, Charleston, SC 29403"
    assert payload["latitude"] == 32.7904936
    assert payload["longitude"] == -79.9375534
    assert "offline" in payload["provider"].lower()


def test_geocode_endpoint_returns_coordinates(monkeypatch):
    client = TestClient(app)

    monkeypatch.setattr(
        "backend.app.main.geocode_location",
        lambda location: {
            "location": location,
            "latitude": 40.7128,
            "longitude": -74.006,
            "display_name": "New York, NY",
            "street_address": "New York, NY",
            "provider": "test",
            "maps_url": "geo:40.7128,-74.006",
        },
    )

    response = client.get("/api/geocode", params={"location": "New York, NY"})

    assert response.status_code == 200
    assert response.json()["latitude"] == 40.7128
    assert response.json()["maps_url"].startswith("geo:")


def test_resources_tasks_nodes_and_ai_outputs_are_functional():
    client = TestClient(app)

    resource = client.post(
        "/api/resources",
        json={"name": "Rescue Team Alpha", "type": "RESCUE", "status": "AVAILABLE", "location": "HQ", "capacity": 4},
    )
    assert resource.status_code == 200
    assert resource.json()["name"] == "Rescue Team Alpha"

    task = client.post(
        "/api/tasks",
        json={"title": "Check East Bay alternate route", "priority": "HIGH", "assigned_resource": "Rescue Team Alpha"},
    )
    assert task.status_code == 200
    assert task.json()["status"] == "OPEN"

    node = client.post(
        "/api/nodes",
        json={"node_name": "NODE07", "battery": 88, "status": "ONLINE", "latitude": 32.78, "longitude": -79.93},
    )
    assert node.status_code == 200
    assert node.json()["node_name"] == "NODE07"

    plan = client.post("/api/ai/plan", json={"constraint": "Only Rescue Team Alpha is available"})
    assert plan.status_code == 200
    assert "ordered_actions" in plan.json()
    assert plan.json()["requires_human_approval"] is True

    briefing = client.post("/api/ai/briefing", json={})
    assert briefing.status_code == 200
    assert "briefing" in briefing.json()


def test_mesh_message_creates_real_incident():
    client = TestClient(app)

    response = client.post(
        "/api/mesh/message",
        json={"node": "NODE07", "type": "MEDICAL", "priority": "URGENT", "lat": 32.78, "lon": -79.93, "message": "One injured person"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "LORA_SIM"
    assert payload["node_id"] == "NODE07"
    assert payload["severity"] in {"CRITICAL", "HIGH"}


def test_records_can_be_removed_from_operational_board():
    client = TestClient(app)

    incident = client.post("/api/incidents", json={"description": "Remove test incident", "category": "TEST"}).json()
    resource = client.post("/api/resources", json={"name": "Remove test resource", "type": "TEST"}).json()
    task = client.post("/api/tasks", json={"title": "Remove test task"}).json()
    node = client.post("/api/nodes", json={"node_name": "REMOVE-NODE"}).json()

    for path, item in [
        ("incidents", incident),
        ("resources", resource),
        ("tasks", task),
        ("nodes", node),
    ]:
        delete_response = client.delete(f"/api/{path}/{item['id']}")
        assert delete_response.status_code == 200
        assert delete_response.json() == {"removed": True, "id": item["id"]}
        assert client.delete(f"/api/{path}/{item['id']}").status_code == 404
