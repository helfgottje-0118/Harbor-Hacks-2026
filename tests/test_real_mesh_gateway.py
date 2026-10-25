"""No radio required: tests authentication, message gating and idempotence."""
from fastapi.testclient import TestClient
from backend.app.main import app
from scripts.harbor_meshtastic_mac import extract_report


def test_mac_receiver_ignores_self_and_non_harbor_chat():
    assert extract_report({"from": 42, "id": 7, "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "HARBOR REPORT: Test"}}, 42) is None
    assert extract_report({"from": 43, "id": 7, "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "Good morning"}}, 42) is None
    got = extract_report({"from": 43, "fromId": "!abc", "id": 7, "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "HARBOR REPORT: Test"}}, 42)
    assert got["sender"] == "!abc"
    assert got["packet_id"] == "7"


def test_authenticated_real_packet_is_saved_once(monkeypatch):
    monkeypatch.setenv("HARBOR_MESH_GATEWAY_TOKEN", "test-secret-only")
    with TestClient(app) as client:
        packet = {"packet_id": "packet-case-101", "sender": "!test-sender", "receiver": "!other", "message": "HARBOR REPORT: Tree blocking the road"}
        url = "/api/mesh/real/receive"
        assert client.post(url, json=packet).status_code == 401
        headers = {"Authorization": "Bearer test-secret-only"}
        ignored = client.post(url, headers=headers, json={**packet, "message": "Hi everyone"})
        assert ignored.status_code == 200
        assert ignored.json()["status"] == "ignored"
        created = client.post(url, headers=headers, json=packet)
        assert created.status_code == 200
        incident_id = created.json()["incident_id"]
        assert created.json()["source"] == "LORA_REAL"
        duplicate = client.post(url, headers=headers, json=packet)
        assert duplicate.json()["status"] == "duplicate"
        assert duplicate.json()["incident_id"] == incident_id
        incident = client.get(f"/api/incidents/{incident_id}").json()
        assert incident["source"] == "LORA_REAL"
        assert incident["node_id"] == "!test-sender"
        assert client.delete(f"/api/incidents/{incident_id}").status_code == 200


def test_mac_terminal_monitor_prints_only_new_saved_reports():
    from scripts.harbor_meshtastic_mac import new_saved_reports
    seen = {13}
    rows = [
        {"id": 14, "source": "LORA_REAL", "description": "A"},
        {"id": 13, "source": "LORA_REAL", "description": "Old"},
    ]
    assert [i["id"] for i in new_saved_reports(rows, seen)] == [14]
    assert new_saved_reports(rows, seen) == []


def test_radio_ai_commands_and_short_replies():
    from scripts.harbor_meshtastic_mac import incoming_command, outgoing_text
    packet = {"from": 99, "fromId": "!remote", "id": 10, "decoded": {
        "portnum": "TEXT_MESSAGE_APP", "text": "HARBOR AI: What should I do during flooding?"
    }}
    assert incoming_command(packet, 12) == ("ai", "What should I do during flooding?")
    assert incoming_command(packet, 99) is None
    packet["decoded"]["text"] = "HARBOR REPORT: Tree blocking roadway"
    assert incoming_command(packet, 12) == ("report", "Tree blocking roadway")
    packet["decoded"]["text"] = "ordinary conversation"
    assert incoming_command(packet, 12) is None
    assert len(outgoing_text("🚨" * 100).encode("utf-8")) <= 180
