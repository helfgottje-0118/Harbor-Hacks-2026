from fastapi.testclient import TestClient
from backend.app.main import app

def test_critical_report_creates_internal_alert_and_can_be_acknowledged():
    with TestClient(app) as client:
        created = client.post("/api/incidents", json={
            "description": "Unresponsive person on road, reportedly not breathing",
            "category": "MEDICAL",
            "people_affected": 1,
            "source": "WEB",
        })
        assert created.status_code == 200
        incident = created.json()
        assert incident["severity"] == "CRITICAL"
        result = client.get("/api/alerts/critical")
        assert result.status_code == 200
        matches = [alert for alert in result.json() if alert["incident_id"] == incident["id"]]
        assert len(matches) == 1
        assert matches[0]["acknowledged_at"] is None
        assert matches[0]["notification_scope"] == "HARBOR_DASHBOARD_ONLY"
        ack = client.post(f'/api/alerts/critical/{matches[0]["id"]}/acknowledge')
        assert ack.status_code == 200
        assert ack.json()["acknowledged_at"]
        assert client.post(f'/api/alerts/critical/{matches[0]["id"]}/acknowledge').status_code == 200
        assert client.delete(f'/api/incidents/{incident["id"]}').status_code == 200
