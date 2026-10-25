"""Prepare a clipped, local Charleston map pack from downloaded source JSON.

Install scripts/requirements-maps.txt. See docs/offline-maps.md for download commands.
Never infers hazard geometry or current flooding from the road map.
"""
from shapely.geometry import box, mapping, shape, LineString
from shapely import make_valid

BBOX = [-80.02, 32.70, -79.84, 32.86]
AREA = box(BBOX[0], BBOX[1], BBOX[2], BBOX[3])


def fema_features(raw, expected_ids):
    features = raw.get('features', [])
    ids = [f['properties']['OBJECTID'] for f in features]
    if raw.get('error') or raw.get('exceededTransferLimit') or set(ids) != set(expected_ids) or len(ids) != len(set(ids)):
        raise ValueError('FEMA download incomplete; retrieve all matching object IDs')
    result = []
    for feature in features:
        geometry = make_valid(shape(feature['geometry'])).intersection(AREA)
        if geometry.is_empty:
            continue
        if geometry.geom_type == 'GeometryCollection':
            from shapely.ops import unary_union
            geometry = unary_union([g for g in geometry.geoms if g.geom_type in ('Polygon', 'MultiPolygon')])
        if geometry.geom_type not in ('Polygon', 'MultiPolygon') or geometry.is_empty:
            continue
        result.append({**feature, 'geometry': mapping(geometry)})
    return result


def osm_features(raw):
    if raw.get('remark'):
        raise ValueError('OSM download incomplete: ' + raw['remark'])
    features = []
    for item in raw.get('elements', []):
        coords = [(p['lon'], p['lat']) for p in item.get('geometry', [])]
        if item.get('type') != 'way' or len(coords) < 2:
            continue
        geometry = LineString(coords).intersection(AREA)
        if geometry.is_empty or geometry.geom_type not in ('LineString', 'MultiLineString'):
            continue
        features.append({'type': 'Feature', 'id': item['id'], 'properties': item.get('tags', {}), 'geometry': mapping(geometry)})
    return features


def write_pack(output, roads, zones, downloaded_at, osm_timestamp):
    import json
    import hashlib
    output.mkdir(parents=True, exist_ok=True)
    sources = {}
    definitions = [
        ('basemap', 'basemap.geojson', roads, 'OpenStreetMap contributors', 'https://overpass.private.coffee/api/interpreter', 'ODbL 1.0; https://www.openstreetmap.org/copyright'),
        ('flood_zones', 'flood-zones.geojson', zones, 'FEMA National Flood Hazard Layer (NFHL)', 'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28', 'US federal flood hazard data; FEMA limitations apply'),
    ]
    for key, filename, features, source, url, license_text in definitions:
        content = json.dumps({'type': 'FeatureCollection', 'bbox': BBOX, 'features': features}, separators=(',', ':'), allow_nan=False).encode()
        temp = output / (filename + '.tmp')
        temp.write_bytes(content)
        temp.replace(output / filename)
        sources[key] = {'file': filename, 'source': source, 'url': url, 'downloaded_at': downloaded_at, 'feature_count': len(features), 'sha256': hashlib.sha256(content).hexdigest(), 'license': license_text}
    sources['basemap']['source_timestamp'] = osm_timestamp
    manifest = {'version': 1, 'area': 'Charleston central-area snapshot (not the entire county)', 'bbox': BBOX, 'sources': sources, 'limitations': 'Static risk zones, not current water extent or depth. Absence of shading does not mean safe. Street lines only; no routing or passability. FEMA geometry generalized at 0.00001 degrees and clipped to coverage.'}
    temp = output / 'manifest.json.tmp'
    temp.write_text(json.dumps(manifest, indent=2) + '\n')
    temp.replace(output / 'manifest.json')
    return manifest


if __name__ == '__main__':
    import argparse
    import json
    from datetime import datetime, timezone
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--osm', type=Path, required=True)
    parser.add_argument('--fema', type=Path, required=True)
    parser.add_argument('--fema-ids', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'data/maps')
    args = parser.parse_args()
    raw_osm = json.loads(args.osm.read_text())
    raw_fema = json.loads(args.fema.read_text())
    ids = json.loads(args.fema_ids.read_text())['objectIds']
    roads = osm_features(raw_osm)
    zones = fema_features(raw_fema, ids)
    if not roads or not zones:
        raise SystemExit('Refusing to publish an empty Charleston map pack')
    fetched = datetime.fromtimestamp(min(args.osm.stat().st_mtime, args.fema.stat().st_mtime), timezone.utc).isoformat()
    manifest = write_pack(args.output, roads, zones, fetched, raw_osm.get('osm3s', {}).get('timestamp_osm_base'))
    print(json.dumps(manifest, indent=2))

