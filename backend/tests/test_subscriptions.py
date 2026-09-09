from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_device_registration_and_alert_subscriptions():
    device = 'test-device-001'
    register = client.post('/v1/device/register', json={'device_id': device})
    assert register.status_code == 200
    assert register.json()['status'] == 'accepted'

    created = client.post('/v1/alerts/subscriptions', json={
        'device_id': device,
        'latitude': 28.6,
        'longitude': 77.2,
        'timezone': 'Asia/Kolkata',
        'channels': ['severe', 'rain'],
    })
    assert created.status_code == 200
    subscription_id = created.json()['subscription']['id']

    listed = client.get('/v1/alerts/subscriptions', params={'device_id': device})
    assert listed.status_code == 200
    assert len(listed.json()['subscriptions']) == 1

    deleted = client.delete(f'/v1/alerts/subscriptions/{subscription_id}', params={'device_id': device})
    assert deleted.status_code == 200
    assert deleted.json()['deleted'] is True
