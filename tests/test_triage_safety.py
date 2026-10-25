from backend.app import ai


def test_tree_blockage_includes_safety_and_review(monkeypatch):
    monkeypatch.setattr(ai, "try_ollama_triage", lambda *args: None)
    result = ai.triage("A tree is blocking 4 Line Street")
    assert result["category"] == "INFRASTRUCTURE"
    assert result["severity"] == "MEDIUM"
    assert "downed wires" in result["recommended_action"]
    assert "human incident review" in result["recommended_action"]
    assert "qualified" in result["recommended_action"]


def test_ollama_cannot_replace_safety_guidance_or_downgrade(monkeypatch):
    monkeypatch.setattr(ai, "try_ollama_triage", lambda *args: {
        "severity": "LOW",
        "category": "INFRASTRUCTURE",
        "recommended_action": "Clear tree",
        "people_affected": 0,
    })
    result = ai.triage("A tree is blocking 4 Line Street")
    assert result["severity"] == "MEDIUM"
    assert result["recommended_action"] != "Clear tree"
    assert "downed wires" in result["recommended_action"]


def test_reported_dead_body_is_medical_not_road_obstruction(monkeypatch):
    monkeypatch.setattr(ai, "try_ollama_triage", lambda *args: {
        "severity": "LOW",
        "recommended_action": "Clear tree",
        "category": "INFRASTRUCTURE",
    })
    result = ai.triage("there is a dead body in the street on 56 george street", "INFRASTRUCTURE")
    assert result["category"] == "MEDICAL"
    assert result["severity"] == "CRITICAL"
    assert "emergency services immediately" in result["recommended_action"]
    assert "move the tree" not in result["recommended_action"].lower()


def test_unresponsive_person_has_medical_guidance_without_ollama(monkeypatch):
    monkeypatch.setattr(ai, "try_ollama_triage", lambda *args: None)
    result = ai.triage("Unresponsive person near a crosswalk")
    assert result["category"] == "MEDICAL"
    assert result["severity"] == "CRITICAL"
    assert "CPR" in result["recommended_action"]
