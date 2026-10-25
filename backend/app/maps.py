"""Offline map pack routes: fixed local files, never upstream requests."""
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

MAPS_DIR = Path(__file__).resolve().parents[2] / "data" / "maps"
LEGACY_MAPS_DIR = Path.home() / "harbor" / "harbor_update" / "data" / "maps"


def map_directory() -> Path:
    configured = os.getenv("HARBOR_MAPS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    # Keep layers from a single map pack, never mix snapshots.
    for candidate in (MAPS_DIR, LEGACY_MAPS_DIR):
        if all((candidate / name).is_file() for name in LAYERS.values()):
            return candidate
    return MAPS_DIR
LAYERS = {"basemap": "basemap.geojson", "flood_zones": "flood-zones.geojson"}
router = APIRouter(prefix="/api/maps", tags=["maps"])


def read_local(filename: str) -> dict:
    """Only callers' fixed filenames are used, never manifest file/URL values."""
    try:
        directory = map_directory()
        path = directory / filename
        if path.resolve().parent != directory.resolve():
            raise ValueError("Map path escapes pack directory")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        if filename.endswith(".geojson") and (
            data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list)
        ):
            raise ValueError("Expected GeoJSON FeatureCollection")
        return data
    except (OSError, ValueError) as exc:
        raise HTTPException(503, detail=f"Offline map data unavailable: {filename}") from exc


@router.get("/manifest")
def manifest():
    data = read_local("manifest.json")
    sources = data.get("sources")
    if not isinstance(sources, dict) or any(not isinstance(sources.get(key), dict) for key in LAYERS):
        raise HTTPException(503, detail="Offline map manifest unavailable: missing source metadata")
    for key, filename in LAYERS.items():
        try:
            read_local(filename)
            sources[key]["available"] = True
        except HTTPException:
            sources[key]["available"] = False
    data["available"] = all(sources[key]["available"] for key in LAYERS)
    return data


@router.get("/basemap.geojson")
def basemap():
    return JSONResponse(read_local(LAYERS["basemap"]), media_type="application/geo+json")


@router.get("/flood-zones.geojson")
def flood_zones():
    return JSONResponse(read_local(LAYERS["flood_zones"]), media_type="application/geo+json")
