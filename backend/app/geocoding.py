import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CACHE_FILE = Path(__file__).resolve().parents[2] / "data" / "geocode_cache.json"

OFFLINE_LOCATIONS: dict[str, dict[str, object]] = {
    "harborwalk": {
        "latitude": 32.7912,
        "longitude": -79.9266406,
        "display_name": "College of Charleston Harbor Walk, 360 Concord Street, Charleston, SC 29401",
        "street_address": "360 Concord Street, Charleston, SC 29401",
    },
    "harbor walk": {
        "latitude": 32.7912,
        "longitude": -79.9266406,
        "display_name": "College of Charleston Harbor Walk, 360 Concord Street, Charleston, SC 29401",
        "street_address": "360 Concord Street, Charleston, SC 29401",
    },
    "harborwalk college of charleston": {
        "latitude": 32.7912,
        "longitude": -79.9266406,
        "display_name": "College of Charleston Harbor Walk, 360 Concord Street, Charleston, SC 29401",
        "street_address": "360 Concord Street, Charleston, SC 29401",
    },
    "360 concord street charleston sc": {
        "latitude": 32.7912,
        "longitude": -79.9266406,
        "display_name": "College of Charleston Harbor Walk, 360 Concord Street, Charleston, SC 29401",
        "street_address": "360 Concord Street, Charleston, SC 29401",
    },
    "66 george street charleston sc": {
        "latitude": 32.7840902,
        "longitude": -79.9380024,
        "display_name": "66 George Street, Charleston, SC 29424",
        "street_address": "66 George Street, Charleston, SC 29424",
    },
    "66 george street charleston": {
        "latitude": 32.7840902,
        "longitude": -79.9380024,
        "display_name": "66 George Street, Charleston, SC 29424",
        "street_address": "66 George Street, Charleston, SC 29424",
    },
    "66 george st charleston sc": {
        "latitude": 32.7840902,
        "longitude": -79.9380024,
        "display_name": "66 George Street, Charleston, SC 29424",
        "street_address": "66 George Street, Charleston, SC 29424",
    },
    "66 george st charleston": {
        "latitude": 32.7840902,
        "longitude": -79.9380024,
        "display_name": "66 George Street, Charleston, SC 29424",
        "street_address": "66 George Street, Charleston, SC 29424",
    },
    "4 line street charleston sc": {
        "latitude": 32.7973582,
        "longitude": -79.9379599,
        "display_name": "4 Line Street, Charleston, SC 29403",
        "street_address": "4 Line Street, Charleston, SC 29403",
    },
    "4 line street charleston": {
        "latitude": 32.7973582,
        "longitude": -79.9379599,
        "display_name": "4 Line Street, Charleston, SC 29403",
        "street_address": "4 Line Street, Charleston, SC 29403",
    },
    "east bay street charleston sc": {
        "latitude": 32.7812804,
        "longitude": -79.9273939,
        "display_name": "East Bay Street, Charleston, SC",
        "street_address": "East Bay Street, Charleston, SC",
    },
    "east bay street charleston": {
        "latitude": 32.7812804,
        "longitude": -79.9273939,
        "display_name": "East Bay Street, Charleston, SC",
        "street_address": "East Bay Street, Charleston, SC",
    },
    "charleston school of law": {
        "latitude": 32.7904936,
        "longitude": -79.9375534,
        "display_name": "Charleston School of Law, 385 Meeting Street, Charleston, SC 29403",
        "street_address": "385 Meeting Street, Charleston, SC 29403",
    },
    "charleston school of law charleston sc": {
        "latitude": 32.7904936,
        "longitude": -79.9375534,
        "display_name": "Charleston School of Law, 385 Meeting Street, Charleston, SC 29403",
        "street_address": "385 Meeting Street, Charleston, SC 29403",
    },
    "shelter a charleston": {
        "latitude": 32.7767,
        "longitude": -79.9311,
        "display_name": "Shelter A, Charleston offline demo location",
        "street_address": "Shelter A, Charleston offline demo location",
    },
    "shelter b charleston": {
        "latitude": 32.7865,
        "longitude": -79.9402,
        "display_name": "Shelter B, Charleston offline demo location",
        "street_address": "Shelter B, Charleston offline demo location",
    },
}

ADDRESS_PATTERNS = [
    re.compile(r"\b\d{1,6}\s*line\s+(?:street|st)\b(?:\s+charleston(?:\s+sc)?)?", re.I),
    re.compile(r"\b\d{1,6}\s+[a-z0-9 .'-]+\s+(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr)\b(?:\s+charleston(?:\s+sc)?)?", re.I),
    re.compile(r"\beast\s+bay\s+(?:street|st)\b(?:\s+charleston(?:\s+sc)?)?", re.I),
    re.compile(r"\bshelter\s+[ab]\b(?:\s+charleston)?", re.I),
]

PLACE_PATTERNS = [
    re.compile(r"\bcharleston\s+school\s+of\s+law\b", re.I),
    re.compile(r"\bharbor\s*walk(?:\s+college\s+of\s+charleston)?\b", re.I),
]

NOISE_WORDS = re.compile(
    r"\b(tree|blocking|blocked|down|with|one|injured|person|people|medical|emergency|fire|flood|near|at|outside|reported|report)\b",
    re.I,
)


def normalize_location(location: str) -> str:
    text = location.lower().replace(",", " ").replace(".", " ")
    text = re.sub(r"\bsouth carolina\b", "sc", text)
    text = re.sub(r"\b(\d{1,6})(line\s+(?:street|st)\b)", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_location(text: str) -> str | None:
    for pattern in ADDRESS_PATTERNS:
        match = pattern.search(text)
        if match:
            location = match.group(0).strip(" ,.;:-")
            if "charleston" not in location.lower():
                location = f"{location}, Charleston, SC"
            return location
    for pattern in PLACE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip(" ,.;:-")
    return None


def _clean_report_text_for_geocoding(text: str) -> str:
    cleaned = NOISE_WORDS.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
    if cleaned and "charleston" not in cleaned.lower():
        cleaned = f"{cleaned}, Charleston, SC"
    return cleaned


def _format_result(query: str, raw: dict[str, object], provider: str) -> dict[str, object]:
    lat = float(raw["latitude"])
    lon = float(raw["longitude"])
    street_address = raw.get("street_address") or raw.get("display_name") or query
    return {
        "location": query,
        "latitude": lat,
        "longitude": lon,
        "display_name": str(raw["display_name"]),
        "street_address": str(street_address),
        "provider": provider,
        "maps_url": f"geo:{lat},{lon}",
    }


def _load_cache() -> dict[str, dict[str, object]]:
    try:
        return json.loads(CACHE_FILE.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict[str, dict[str, object]]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, sort_keys=True))


def _candidate_keys(query: str) -> list[str]:
    normalized = normalize_location(query)
    candidates = [normalized]
    if "charleston" not in normalized:
        candidates.extend([f"{normalized} charleston sc", f"{normalized} charleston"])
    if " sc" not in normalized and "charleston" in normalized:
        candidates.append(f"{normalized} sc")
    return list(dict.fromkeys(candidates))


def _online_geocode(query: str) -> dict[str, object] | None:
    search_query = query if "charleston" in query.lower() else f"{query}, Charleston, SC"
    params = urlencode({"q": search_query, "format": "jsonv2", "limit": 1, "addressdetails": 1})
    req = Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": "HARBOR-offline-emergency-command/0.5"},
    )
    try:
        with urlopen(req, timeout=6) as response:
            results = json.loads(response.read().decode())
    except Exception:
        return None
    if not results:
        return None
    first = results[0]
    address = first.get("address") or {}
    house = address.get("house_number")
    road = address.get("road")
    city = address.get("city") or address.get("town") or address.get("village") or "Charleston"
    state = address.get("state") or "SC"
    postcode = address.get("postcode")
    if house and road:
        street_address = f"{house} {road}, {city}, {state}" + (f" {postcode}" if postcode else "")
    else:
        street_address = first.get("display_name", search_query)
    return {
        "latitude": float(first["lat"]),
        "longitude": float(first["lon"]),
        "display_name": first.get("display_name", search_query),
        "street_address": street_address,
    }


@lru_cache(maxsize=256)
def geocode_location(location: str) -> dict[str, object] | None:
    query = normalize_location(location)
    if not query:
        return None

    candidates = _candidate_keys(query)
    cache = _load_cache()

    for candidate in candidates:
        if candidate in OFFLINE_LOCATIONS:
            return _format_result(query, OFFLINE_LOCATIONS[candidate], "HARBOR offline Charleston gazetteer")
        if candidate in cache:
            return _format_result(query, cache[candidate], "HARBOR local geocode cache")

    online = _online_geocode(query)
    if not online:
        return None

    for candidate in candidates:
        cache[candidate] = online
    _save_cache(cache)
    return _format_result(query, online, "OpenStreetMap Nominatim online fallback; cached for offline reuse")


def geocode_text(location: str | None, description: str) -> dict[str, object] | None:
    if location:
        result = geocode_location(location)
        if result:
            return result
    extracted = extract_location(description)
    if extracted:
        result = geocode_location(extracted)
        if result:
            return result
    # Do not guess a location from incident narrative: a matching city/address
    # is required before assigning map coordinates to emergency reports.
    return None
