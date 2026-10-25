# Offline Charleston map pack

## Scope and safety

The bundled map covers **central Charleston**, bounds west/south/east/north
`[-80.02, 32.70, -79.84, 32.86]`; it does not cover all of Charleston County.
It uses real OpenStreetMap highway linework and FEMA National Flood Hazard Layer
(NFHL) polygons, downloaded before use and served by the local HARBOR computer.
No internet tile service or CDN is required. HARBOR must still be running and
reachable over a local network; this is not a standalone phone/PWA cache.

- Flood zones describe **risk**, not water currently present or current depth.
- Unshaded areas are not guaranteed safe. Reports are unverified observations,
  not a continuous flood-extent model. Do not infer safe routes from this map.
- Resource locations require coordinates; a name such as "HQ" is not sufficient.
- The base map is street-line context, not a full cartographic/terrain basemap.
- `manifest.json` records source, acquisition date, counts, bounds and SHA-256.
  OSM's own `source_timestamp` can predate the download. Download date is not
  the effective date of every FEMA study.
- FEMA polygons are generalized at 0.00001 degrees and clipped to the coverage
  boundary. Consult FEMA's current official products for regulatory decisions.
- LoRa remains **simulation only**. `/api/mesh/message` accepts decoded JSON for
  development and labels it `LORA_SIM`; no radio, serial driver, authentication
  handshake, or live receiver is implied. Hardware integration remains separate.
- Protect the existing unauthenticated application behind a trusted local
  network or authenticated reverse proxy before handling sensitive reports.

## Attribution

Street data © OpenStreetMap contributors, available under [ODbL 1.0](https://www.openstreetmap.org/copyright).
The clipped road dataset retains OSM tags and IDs; redistribution is under ODbL.

Flood data: [FEMA NFHL](https://hazards.fema.gov/femaportal/resources/flood_map_svc.htm),
[official Flood Hazard Zones service](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28).
The original `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, study and source IDs are retained.
Do not interpret every FEMA polygon as high risk: minimal-hazard X zones must not
receive the same shading as Special Flood Hazard Areas; 0.2-percent annual-chance
zones are a separate risk class.

## Refresh the pack while online

Do not bulk-download tiles from the public OpenStreetMap tile server. Instead
use the bounded Overpass vector query below. The downloads are performed manually,
not during app startup or incident polling. Public services may throttle/fail;
keep the last good pack until a complete replacement is prepared.

```bash
cd /root/harbor
.venv/bin/pip install -r scripts/requirements-maps.txt
mkdir -p /tmp/harbor-map-refresh
curl --fail --max-time 180 --get \
  --data-urlencode 'data=[out:json][timeout:100];way["highway"](32.70,-80.02,32.86,-79.84);out geom;' \
  'https://overpass.private.coffee/api/interpreter' \
  -o /tmp/harbor-map-refresh/osm.json

FEMA='https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query'
curl --fail --max-time 180 --get "$FEMA" \
  --data-urlencode 'where=1=1' \
  --data-urlencode 'geometry=-80.02,32.70,-79.84,32.86' \
  --data-urlencode 'geometryType=esriGeometryEnvelope' \
  --data-urlencode 'inSR=4326' --data-urlencode 'spatialRel=esriSpatialRelIntersects' \
  --data-urlencode 'returnIdsOnly=true' --data-urlencode 'f=json' \
  -o /tmp/harbor-map-refresh/fema-ids.json
curl --fail --max-time 180 --get "$FEMA" \
  --data-urlencode 'where=1=1' \
  --data-urlencode 'geometry=-80.02,32.70,-79.84,32.86' \
  --data-urlencode 'geometryType=esriGeometryEnvelope' \
  --data-urlencode 'inSR=4326' --data-urlencode 'spatialRel=esriSpatialRelIntersects' \
  --data-urlencode 'outFields=OBJECTID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,DFIRM_ID,SOURCE_CIT' \
  --data-urlencode 'outSR=4326' --data-urlencode 'returnGeometry=true' \
  --data-urlencode 'maxAllowableOffset=0.00001' --data-urlencode 'geometryPrecision=6' \
  --data-urlencode 'f=geojson' -o /tmp/harbor-map-refresh/fema.geojson
.venv/bin/python scripts/prepare_maps.py \
  --osm /tmp/harbor-map-refresh/osm.json \
  --fema /tmp/harbor-map-refresh/fema.geojson \
  --fema-ids /tmp/harbor-map-refresh/fema-ids.json \
  --output /tmp/harbor-map-refresh/pack
.venv/bin/pytest scripts/test_prepare_maps.py -q
```

The preparation command checks returned FEMA IDs against the independent complete
ID query and rejects truncated downloads. If FEMA's record limit is exceeded,
fetch those object IDs in batches, combine the GeoJSON features, then rerun
preparation; do not accept a partial pack. Update `data/maps` only after validation,
with HARBOR stopped briefly to avoid mixing pack versions, and retain a backup.
The optional Shapely dependency is only needed for preparation, not map serving.

## API fields

Incident and simulated mesh payloads accept optional `water_depth_cm` (nonnegative,
null means unknown) and `observed_at` (timezone-aware ISO-8601). Report receipt
`timestamp` remains separate. A reported zero is not missing data.
Resource payloads accept paired `latitude` and `longitude`.
All map requests use local `/api/maps/` endpoints; missing packs must be reported
as unavailable, never substituted with invented flood zones.

Example **simulation**, not a real emergency report:

```json
{
  "node": "TEST-NODE",
  "type": "FLOOD",
  "priority": "NORMAL",
  "lat": 32.78,
  "lon": -79.93,
  "message": "TEST ONLY: simulated water observation",
  "water_depth_cm": 15,
  "observed_at": "2026-10-11T12:00:00Z"
}
```

## Verification

Run backend tests, map-preparation tests, frontend tests and the production build.
For a true offline-map check, load the app in a browser that blocks every non-local
request while leaving the HARBOR server reachable. Confirm risk layers, streets,
report/resource markers and popups still work, and that no external network
requests are needed. A successful build alone is not that verification.
