import asyncio
from unittest.mock import Mock
import pytest
from fastapi import HTTPException

from backend.app.forge_bridge import forge_endpoint, forge_reply
from backend.app.main import app
from fastapi.testclient import TestClient


def test_forge_is_default_provider_with_authenticated_server_side_request(monkeypatch):
    monkeypatch.delenv("HARBOR_AI_PROVIDER", raising=False)
    monkeypatch.setenv("FORGE_WEBUI_TOKEN", "x" * 40)
    monkeypatch.setenv("FORGE_BACKEND_URL", "http://127.0.0.1:8765")
    observed = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"ok": True, "reply": "Call emergency services if anyone is in immediate danger."}

    class FakeClient:
        def __init__(self, **kwargs): observed["client_kwargs"] = kwargs
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, headers, json):
            observed.update(url=url, headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr("backend.app.forge_bridge.httpx.AsyncClient", FakeClient)
    result = TestClient(app).post("/api/ai/chat", json={"message": "I need fire safety advice"})
    assert result.status_code == 200
    assert result.json()["source"] == "forge"
    assert "emergency services" in result.json()["reply"]
    assert observed["url"] == "http://127.0.0.1:8765/api/agent/chat"
    assert observed["headers"]["Authorization"] == "Bearer " + "x" * 40
    assert observed["client_kwargs"]["trust_env"] is False


def test_forge_requires_token(monkeypatch):
    monkeypatch.delenv("FORGE_WEBUI_TOKEN", raising=False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(forge_reply("hello", []))
    assert error.value.status_code == 503


def test_forge_rejects_remote_url(monkeypatch):
    monkeypatch.setenv("FORGE_BACKEND_URL", "https://forge.example.com")
    with pytest.raises(HTTPException) as error:
        forge_endpoint()
    assert error.value.status_code == 503


def test_report_drafting_still_bypasses_forge(monkeypatch):
    monkeypatch.delenv("FORGE_WEBUI_TOKEN", raising=False)
    monkeypatch.delenv("HARBOR_AI_PROVIDER", raising=False)
    response = TestClient(app).post("/api/ai/chat", json={
        "message": "Create a report for power loss at 4 Line Street"
    })
    assert response.status_code == 200
    assert response.json()["report_draft"]["requires_confirmation"] is True
