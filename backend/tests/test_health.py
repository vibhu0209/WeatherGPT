from fastapi.testclient import TestClient
from app.main import app


def test_health():
    body = TestClient(app).get('/health').json()
    assert body['status'] == 'ok'


def test_capabilities_report_disabled_cloud_delivery():
    body = TestClient(app).get('/v1/capabilities').json()
    assert body['cloud_voice'] is False
    assert body['demo_mode'] is False
    assert 'google_places_configured' in body
    assert 'google_places_enabled' in body
    assert isinstance(body['google_places_configured'], bool)
    assert isinstance(body['google_places_enabled'], bool)
    assert body['google_places_enabled'] is False
    transports = {item['transport']: item['status'] for item in body['alert_delivery']}
    assert transports == {'fcm': 'disabled', 'sms': 'disabled'}
