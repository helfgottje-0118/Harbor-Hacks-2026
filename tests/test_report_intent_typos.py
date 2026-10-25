from backend.app.ai_chat import Message, build_report_draft, wants_report_submission


def test_report_request_typo_routes_to_draft():
    message = "can u help submit a reprot for a fire at harbor walk 24 people"
    assert wants_report_submission(message)
    draft = build_report_draft([Message(role="user", content=message)])
    assert draft["category"] == "FIRE"
    assert draft["people_affected"] == 24
    assert "fire at harbor walk" in draft["description"].lower()
    assert draft["requires_confirmation"] is True


def test_generic_report_help_routes_to_draft():
    assert wants_report_submission("can u help submit a reprot")
    assert wants_report_submission("can you help submit a report")
    assert wants_report_submission("help submit a report")


def test_followup_help_uses_prior_incident_not_request_wording():
    draft = build_report_draft([
        Message(role="user", content="can u make a report at harborwalk with a fire of 34 persons"),
        Message(role="assistant", content="Review the report before saving."),
        Message(role="user", content="can u write a help"),
    ])
    assert draft["category"] == "FIRE"
    assert draft["people_affected"] == 34
    assert "harborwalk" in draft["description"].lower()
    assert "can u write a help" not in draft["description"].lower()
    assert draft["location"] == "360 Concord St, Charleston, SC"


def test_help_without_incident_does_not_invent_one():
    draft = build_report_draft([Message(role="user", content="can u write a help")])
    assert not draft["description"]
    assert draft["category"] == "UNCLASSIFIED"
