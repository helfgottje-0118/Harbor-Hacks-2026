"""Regression tests for safe PHOTON/LoRa/web landmark mapping."""
from backend.app.geocoding import extract_location, geocode_text


def test_harborwalk_maps_to_concord_street_offline():
    for narrative in (
        "smoke coming from a building at Harborwalk",
        "Fire at Harbor Walk College of Charleston",
    ):
        result = geocode_text(None, narrative)
        assert result is not None
        assert "360 Concord Street" in result["street_address"]
        assert abs(result["latitude"] - 32.7912) < 0.00001
        assert abs(result["longitude"] + 79.9266406) < 0.00001


def test_harborwalk_is_recognized_in_location_field():
    result = geocode_text("Harborwalk", "smoke coming from a building")
    assert result is not None
    assert result["street_address"].startswith("360 Concord Street")


def test_generic_smoke_does_not_invent_coordinates():
    assert extract_location("smoke coming from a building") is None
    assert geocode_text(None, "smoke coming from a building") is None
