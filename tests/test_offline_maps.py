from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import database, main


@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    monkeypatch.setattr(database, 'engine', engine)
    database.Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def get_db():
        with sessions() as session:
            yield session
    main.app.dependency_overrides[database.get_db] = get_db
    monkeypatch.setattr(main.ai, 'triage', lambda *args: {})
    monkeypatch.setattr(main, 'geocode_text', lambda *args: None)
    with TestClient(main.app, raise_server_exceptions=True) as value:
        yield value
    main.app.dependency_overrides.clear()
    engine.dispose()


@pytest.mark.parametrize('route,payload', [
    ('/api/incidents', {'description': 'Flood report'}),
    ('/api/mesh/message', {'node': 'NODE1', 'type': 'FLOOD', 'message': 'Flood report'}),
])
def test_depth_and_observation_survive_receipt(client, route, payload):
    payload.update(water_depth_cm=12.5, observed_at='2020-01-01T08:00:00-05:00')
    response = client.post(route, json=payload)
    assert response.status_code == 200
    report = response.json()
    assert report['water_depth_cm'] == 12.5
    observed = datetime.fromisoformat(report['observed_at'])
    assert observed == datetime(2020, 1, 1, 13, tzinfo=timezone.utc)
    assert datetime.fromisoformat(report['timestamp']).tzinfo is not None
    assert report['timestamp'] != report['observed_at']
    if route.endswith('/message'):
        assert report['source'] == 'LORA_SIM'
    assert client.get(f"/api/incidents/{report['id']}").json() == report
    assert client.get('/api/incidents').json()[0] == report


@pytest.mark.parametrize('route,payload', [
    ('/api/incidents', {'description': 'Flood report'}),
    ('/api/mesh/message', {'node': 'N1', 'type': 'FLOOD', 'message': 'Flood report'}),
])
@pytest.mark.parametrize('invalid', [
    {'water_depth_cm': -1}, {'water_depth_cm': 'NaN'}, {'water_depth_cm': 'Infinity'},
    {'observed_at': '2020-01-01T08:00:00'},
])
def test_report_rejects_invalid_measurements(client, route, payload, invalid):
    assert client.post(route, json={**payload, **invalid}).status_code == 422


@pytest.mark.parametrize('depth', [None, 0])
def test_report_unknown_and_zero_depth_are_distinct(client, depth):
    data = client.post('/api/incidents', json={'description': 'Water', 'water_depth_cm': depth}).json()
    assert data['water_depth_cm'] == depth
    assert data['observed_at'] is None


@pytest.mark.parametrize('coordinates', [{}, {'latitude': None, 'longitude': None}, {'latitude': 32.78, 'longitude': -79.93}, {'latitude': -90, 'longitude': 180}])
def test_resource_coordinates_roundtrip(client, coordinates):
    response = client.post('/api/resources', json={'name': 'Rescue', 'type': 'BOAT', **coordinates})
    assert response.status_code == 200
    resource = response.json()
    assert resource['latitude'] == coordinates.get('latitude')
    assert resource['longitude'] == coordinates.get('longitude')
    assert client.get('/api/resources').json()[0] == resource


@pytest.mark.parametrize('coordinates', [
    {'latitude': 91, 'longitude': 0}, {'latitude': -91, 'longitude': 0},
    {'latitude': 0, 'longitude': 181}, {'latitude': 0, 'longitude': -181},
    {'latitude': 32}, {'longitude': -79}, {'latitude': None, 'longitude': 0},
    {'latitude': 'NaN', 'longitude': 0},
])
def test_resource_coordinates_reject_invalid_pairs(client, coordinates):
    assert client.post('/api/resources', json={'name': 'Rescue', 'type': 'BOAT', **coordinates}).status_code == 422


def test_additive_sqlite_migration_preserves_existing_rows(tmp_path, monkeypatch):
    from sqlalchemy import inspect
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(database, 'engine', engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE incidents (id INTEGER PRIMARY KEY, description TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO incidents VALUES (42, 'Legacy report')")
        connection.exec_driver_sql("CREATE TABLE resources (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO resources VALUES (7, 'Legacy boat')")
    database.init_db()
    database.init_db()
    for table, additions in [('incidents', {'water_depth_cm', 'observed_at'}), ('resources', {'latitude', 'longitude'})]:
        columns = {column['name']: column for column in inspect(engine).get_columns(table)}
        assert additions <= columns.keys()
        assert all(columns[name]['nullable'] for name in additions)
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT * FROM incidents').one() == (42, 'Legacy report', None, None)
        assert connection.exec_driver_sql('SELECT * FROM resources').one() == (7, 'Legacy boat', None, None)
    engine.dispose()


@pytest.fixture
def map_pack(tmp_path, monkeypatch):
    import json
    maps = getattr(main, 'maps', None)
    if maps is not None:
        monkeypatch.setattr(maps, 'MAPS_DIR', tmp_path)
    geojson = {'type': 'FeatureCollection', 'features': []}
    manifest = {'bbox': [-80.02, 32.70, -79.84, 32.86], 'sources': {}}
    for key, file in [('basemap', 'basemap.geojson'), ('flood_zones', 'flood-zones.geojson')]:
        manifest['sources'][key] = {'source': 'Test source', 'url': 'https://example.org/source', 'downloaded_at': '2026-10-01T00:00:00Z', 'feature_count': 0, 'file': file}
        (tmp_path / file).write_text(json.dumps(geojson))
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    return tmp_path, manifest, geojson


def test_local_map_pack_serves_metadata_and_geojson(client, map_pack, monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError('Map routes must not use the network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    directory, manifest, geojson = map_pack
    response = client.get('/api/maps/manifest')
    assert response.status_code == 200
    data = response.json()
    assert data['bbox'] == manifest['bbox']
    assert data['available'] is True
    for key, metadata in manifest['sources'].items():
        assert data['sources'][key]['available'] is True
        for field, value in metadata.items():
            assert data['sources'][key][field] == value
        response = client.get('/api/maps/' + metadata['file'])
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('application/geo+json')
        assert response.json() == geojson


@pytest.mark.parametrize('filename', ['manifest.json', 'basemap.geojson', 'flood-zones.geojson'])
@pytest.mark.parametrize('damage', ['missing', 'invalid'])
def test_map_missing_or_invalid_data_is_explicit_503(client, map_pack, filename, damage):
    directory, _, _ = map_pack
    if damage == 'missing':
        (directory / filename).unlink()
    else:
        (directory / filename).write_text('{}')
    route = 'manifest' if filename == 'manifest.json' else filename
    response = client.get('/api/maps/' + route)
    assert response.status_code == 503
    assert 'unavailable' in response.json()['detail'].lower()
    if filename != 'manifest.json':
        data = client.get('/api/maps/manifest').json()
        key = 'basemap' if filename == 'basemap.geojson' else 'flood_zones'
        assert data['available'] is False
        assert data['sources'][key]['available'] is False
        assert data['sources'][key]['source'] == 'Test source'


def test_map_routes_do_not_follow_manifest_paths_or_serve_other_files(client, map_pack):
    import json
    directory, manifest, _ = map_pack
    manifest['sources']['basemap']['file'] = 'https://example.org/remote.geojson'
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    (directory / 'basemap.geojson').unlink()
    response = client.get('/api/maps/basemap.geojson')
    assert response.status_code == 503
    assert client.get('/api/maps/private.geojson').status_code == 404


def test_map_routes_reject_symlinks_outside_pack(client, map_pack, tmp_path):
    directory, _, _ = map_pack
    outside = directory.parent / (directory.name + '-outside.json')
    outside.write_text('{"type":"FeatureCollection","features":[]}')
    (directory / 'basemap.geojson').unlink()
    (directory / 'basemap.geojson').symlink_to(outside)
    assert client.get('/api/maps/basemap.geojson').status_code == 503
