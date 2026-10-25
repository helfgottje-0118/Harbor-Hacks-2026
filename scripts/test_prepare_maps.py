import importlib.util
from pathlib import Path
import pytest


def module():
    spec = importlib.util.spec_from_file_location('prepare_maps', Path(__file__).with_name('prepare_maps.py'))
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_osm_clips_real_roads_and_keeps_names():
    m = module()
    raw = {'elements': [{'type': 'way', 'id': 1, 'tags': {'highway': 'residential', 'name': 'Test Street'}, 'geometry': [{'lon': -80.1, 'lat': 32.8}, {'lon': -79.9, 'lat': 32.8}]}]}
    result = m.osm_features(raw)
    assert len(result) == 1
    assert result[0]['properties']['name'] == 'Test Street'
    assert result[0]['geometry']['coordinates'][0][0] == -80.02
    with pytest.raises(ValueError, match='incomplete'):
        m.osm_features({'remark': 'timed out', 'elements': []})


def test_fema_requires_complete_ids_and_clips_without_inventing_hazard():
    m = module()
    feature = {'type': 'Feature', 'properties': {'OBJECTID': 1, 'FLD_ZONE': 'AE', 'SFHA_TF': 'T'}, 'geometry': {'type': 'Polygon', 'coordinates': [[[-80.1,32.75],[-79.9,32.75],[-79.9,32.8],[-80.1,32.8],[-80.1,32.75]]]}}
    result = m.fema_features({'type': 'FeatureCollection', 'features': [feature]}, [1])
    assert result[0]['properties']['FLD_ZONE'] == 'AE'
    assert m.shape(result[0]['geometry']).bounds[0] == -80.02
    with pytest.raises(ValueError, match='incomplete'):
        m.fema_features({'type': 'FeatureCollection', 'features': [feature]}, [1, 2])


def test_pack_writes_provenance_and_verifiable_checksums(tmp_path):
    import json, hashlib
    m = module()
    m.write_pack(tmp_path, [{'type': 'Feature', 'properties': {}, 'geometry': {'type': 'LineString', 'coordinates': [[-80,32.8],[-79.9,32.8]]}}], [], '2026-10-11T00:00:00Z', '2026-10-10T00:00:00Z')
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    assert manifest['bbox'] == m.BBOX
    assert manifest['sources']['basemap']['feature_count'] == 1
    assert manifest['sources']['basemap']['sha256'] == hashlib.sha256((tmp_path / 'basemap.geojson').read_bytes()).hexdigest()
    assert manifest['sources']['flood_zones']['source'].startswith('FEMA')


