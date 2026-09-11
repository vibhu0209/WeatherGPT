from fastapi.testclient import TestClient
from app.main import app


def test_health():
    body = TestClient(app).get('/health').json()
    assert body['status'] == 'ok'


def test_capabilities_report_disabled_cloud_delivery():
    body = TestClient(app).get('/v1/capabilities').json()
    assert body['cloud_voice'] is False
    assert body['demo_mode'] is False
    transports = {item['transport']: item['status'] for item in body['alert_delivery']}
    assert transports == {'fcm': 'disabled', 'sms': 'disabled'}
