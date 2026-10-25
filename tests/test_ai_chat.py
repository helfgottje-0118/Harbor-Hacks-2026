from fastapi.testclient import TestClient
from backend.app.main import app


def test_chat_calls_ollama_and_returns_reply(monkeypatch):
    from backend.app import ai_chat
    monkeypatch.setenv('HARBOR_AI_PROVIDER', 'ollama')
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "Move to higher ground if safe."}}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            captured["url"] = url
            captured["body"] = json
            return FakeResponse()

    monkeypatch.setattr(ai_chat.httpx, "AsyncClient", FakeClient)
    res = TestClient(app).post("/api/ai/chat", json={"message": "Floodwater rising"})
    assert res.status_code == 200
    assert res.json()["reply"] == "Move to higher ground if safe."
    assert captured["body"]["messages"][-1]["content"] == "Floodwater rising"


def test_chat_rejects_empty_message():
    res = TestClient(app).post("/api/ai/chat", json={"message": ""})
    assert res.status_code == 422
