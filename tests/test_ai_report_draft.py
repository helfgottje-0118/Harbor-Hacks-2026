from fastapi.testclient import TestClient
from backend.app.main import app


def test_4_line_street_resolves_without_extra_street_number():
    client = TestClient(app)
    response = client.post("/api/ai/report-draft", json={"messages": [
        {"role": "user", "content": "A tree is blocking the road at 4 Line Street"},
        {"role": "assistant", "content": "Can you give me the street number?"},
        {"role": "user", "content": "can you create a report"},
    ]})
    assert response.status_code == 200
    data = response.json()
    assert data["location"] == "4 Line Street, Charleston, SC 29403"
    assert data["location_resolved"] is True
    assert data["category"] == "INFRASTRUCTURE"
    assert data["requires_confirmation"] is True


def test_draft_without_address_does_not_invent_one():
    response = TestClient(app).post("/api/ai/report-draft", json={"messages": [
        {"role": "user", "content": "There is a tree blocking a road"}
    ]})
    assert response.status_code == 200
    assert response.json()["location"] == ""
    assert response.json()["location_resolved"] is False


def test_draft_never_creates_an_incident():
    client = TestClient(app)
    before = len(client.get("/api/incidents").json())
    response = client.post("/api/ai/report-draft", json={"messages": [
        {"role": "user", "content": "Tree at 4 Line Street"}
    ]})
    assert response.status_code == 200
    assert len(client.get("/api/incidents").json()) == before


def test_submit_request_returns_confirmation_form_not_ollama(monkeypatch):
    from backend.app import ai_chat

    class NoOllama:
        def __init__(self, **kwargs):
            raise AssertionError("Report intent must not go to Ollama")

    monkeypatch.setattr(ai_chat.httpx, "AsyncClient", NoOllama)
    response = TestClient(app).post("/api/ai/chat", json={
        "message": "I want it to submit a report for me",
        "history": [
            {"role": "user", "content": "Tree blocking road at 4 Line Street"},
            {"role": "assistant", "content": "Can you give a street number?"}
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["report_draft"]["description"] == "Tree blocking road at 4 Line Street"
    assert data["report_draft"]["location"] == "4 Line Street, Charleston, SC 29403"
    assert data["report_draft"]["requires_confirmation"] is True
    assert "Nothing has been submitted" in data["reply"]


def test_submit_intent_cannot_invent_report_details():
    result = TestClient(app).post("/api/ai/chat", json={
        "message": "submit a report"
    }).json()
    assert result["report_draft"]["description"] == ""
    assert result["report_draft"]["location"] == ""


def test_single_message_with_tree_and_submit_retains_description():
    response = TestClient(app).post("/api/ai/chat", json={
        "message": "there is a tree stuck on 4 line street can u submit a report"
    })
    assert response.status_code == 200
    draft = response.json()["report_draft"]
    assert "tree stuck on 4 line street" in draft["description"].lower()
    assert draft["category"] == "INFRASTRUCTURE"
    assert draft["location"] == "4 Line Street, Charleston, SC 29403"
    assert draft["requires_confirmation"] is True


def test_draft_wording_opens_form_without_model(monkeypatch):
    from backend.app import ai_chat

    class MustNotInvokeModel:
        def __init__(self, **kwargs):
            raise AssertionError("Report requests should open the form")

    monkeypatch.setattr(ai_chat.httpx, "AsyncClient", MustNotInvokeModel)
    response = TestClient(app).post("/api/ai/chat", json={
        "message": "Please help me draft a report",
        "history": [{"role": "user", "content": "A tree is blocking 4 Line Street"}],
    })
    assert response.status_code == 200
    draft = response.json()["report_draft"]
    assert draft["location"] == "4 Line Street, Charleston, SC 29403"
    assert draft["category"] == "INFRASTRUCTURE"
    assert "tree" in draft["description"].lower()


def test_combined_tree_report_intent_keeps_description_and_category():
    response = TestClient(app).post("/api/ai/chat", json={
        "message": "there is a treet stuck on 54 george street help submit a report"
    })
    assert response.status_code == 200
    draft = response.json()["report_draft"]
    assert draft["description"].lower().startswith("there is a treet stuck on 54 george street")
    assert draft["category"] == "INFRASTRUCTURE"
    assert "54 George Street" in draft["location"]
    assert draft["requires_confirmation"] is True


def test_ollama_classification_for_ambiguous_report(monkeypatch):
    import asyncio
    from backend.app.ai_chat import enrich_report_category

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"response": '{"category":"SHELTER"}'}

    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, json): return FakeResponse()

    monkeypatch.setattr("backend.app.ai_chat.httpx.AsyncClient", FakeClient)
    result = asyncio.run(enrich_report_category({
        "description": "A warming center needs supplies",
        "category": "UNCLASSIFIED",
        "location": "",
    }))
    assert result["category"] == "SHELTER"


def test_harborwalk_power_loss_draft_defaults_and_suggestions():
    from datetime import datetime
    draft = TestClient(app).post("/api/ai/report-draft", json={"messages": [
        {"role": "user", "content": "Power loss at Harborwalk College of Charleston affected 40 people"}
    ]})
    assert draft.status_code == 200
    result = draft.json()
    assert result["location"] == "360 Concord St, Charleston, SC"
    assert result["people_affected"] == 40
    assert result["category"] == "INFRASTRUCTURE"
    assert result["datetime_assumed"] is True
    assert datetime.fromisoformat(result["incident_datetime"]).tzinfo is not None
    assert result["actions_taken"] == ""
    assert "power" in result["next_steps"].lower() or "electrical" in result["next_steps"].lower()
    assert result["requires_confirmation"] is True


def test_fire_report_extracts_affected_people_and_is_not_infrastructure():
    response = TestClient(app).post("/api/ai/report-draft", json={"messages": [
        {"role": "user", "content": "give me a report for a fire at 66 george street approximately 34 persons are inside"}
    ]})
    assert response.status_code == 200
    draft = response.json()
    assert draft["category"] == "FIRE"
    assert draft["people_affected"] == 34
    assert draft["location"].lower().startswith("66 george street")


def test_battery_location_correction_preserves_fire_and_people():
    response = TestClient(app).post("/api/ai/chat", json={
        "message": "no its actually at the battery give the address an update",
        "history": [
            {"role": "user", "content": "fire at 66 George Street approximately 34 persons are inside"},
            {"role": "assistant", "content": "Please review the draft before saving."},
        ],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["report_draft"]["category"] == "FIRE"
    assert data["report_draft"]["people_affected"] == 34
    assert data["report_draft"]["location"].startswith("The Battery")
    assert data["report_draft"]["location_resolved"] is False
    assert data["report_draft"]["requires_confirmation"] is True
