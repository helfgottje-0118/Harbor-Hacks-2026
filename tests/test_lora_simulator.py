"""Hardware-free tests for the Harbor LoRa CLI simulator."""
from scripts import harbor_lora_simulator as sim


def test_ai_mode_posts_expected_ollama_payload(monkeypatch):
    calls = []

    def fake_post(url, payload, timeout=120):
        calls.append((url, payload))
        return {"response": "Move to higher ground if safe."}

    monkeypatch.setattr(sim, "post_json", fake_post)
    answer = sim.simulate_ai("Floodwater is rising", "http://ollama:11434/", "test-model")
    assert answer == "Move to higher ground if safe."
    assert calls[0][0] == "http://ollama:11434/api/generate"
    assert calls[0][1]["model"] == "test-model"
    assert "Floodwater is rising" in calls[0][1]["prompt"]
    assert calls[0][1]["stream"] is False


def test_incident_mode_uses_existing_mesh_endpoint(monkeypatch):
    calls = []

    def fake_post(url, payload, timeout=120):
        calls.append((url, payload))
        return {"id": 7, "severity": "HIGH", "source": "LORA_SIM"}

    monkeypatch.setattr(sim, "post_json", fake_post)
    result = sim.simulate_incident(
        "Tree blocking road", "http://harbor:8010/", "SIM-NODE-01"
    )
    assert result["id"] == 7
    assert calls[0][0] == "http://harbor:8010/api/mesh/message"
    assert calls[0][1]["node"] == "SIM-NODE-01"
    assert calls[0][1]["message"] == "Tree blocking road"


def test_cli_single_message(monkeypatch, capsys):
    monkeypatch.setattr(sim, "simulate_ai", lambda *args: "Stay safe.")
    code = sim.main(["--mode", "ai", "--once", "Need assistance"])
    assert code == 0
    output = capsys.readouterr().out
    assert "Stay safe." in output
    assert "NO RADIO TRANSMISSION" in output


def test_cli_rejects_empty_single_message(capsys):
    assert sim.main(["--once", "  "]) == 2
    assert "cannot be empty" in capsys.readouterr().err
