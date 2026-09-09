from fastapi.testclient import TestClient

from app.main import app
from app import subscriptions


client = TestClient(app)


def setup_function():
    subscriptions.reset_for_tests()


def _auth_headers(device_id: str, token: str) -> dict[str, str]:
    return {'X-Device-Id': device_id, 'Authorization': f'Bearer {token}'}


def test_device_registration_and_alert_subscriptions():
    register = client.post('/v1/device/register', json={})
    assert register.status_code == 200
    body = register.json()
    assert body['status'] == 'accepted'
    device = body['device_id']
    token = body['device_token']

    created = client.post('/v1/alerts/subscriptions', headers=_auth_headers(device, token), json={
        'latitude': 28.6,
        'longitude': 77.2,
        'timezone': 'Asia/Kolkata',
        'channels': ['severe', 'rain'],
    })
    assert created.status_code == 200
    subscription_id = created.json()['subscription']['id']

    listed = client.get('/v1/alerts/subscriptions', headers=_auth_headers(device, token))
    assert listed.status_code == 200
    assert len(listed.json()['subscriptions']) == 1

    deleted = client.delete(f'/v1/alerts/subscriptions/{subscription_id}', headers=_auth_headers(device, token))
    assert deleted.status_code == 200
    assert deleted.json()['deleted'] is True


def test_subscriptions_require_device_token_and_isolate_devices():
    first = client.post('/v1/device/register', json={}).json()
    second = client.post('/v1/device/register', json={}).json()

    created = client.post('/v1/alerts/subscriptions', headers=_auth_headers(first['device_id'], first['device_token']), json={
        'latitude': 19.07,
        'longitude': 72.87,
        'timezone': 'Asia/Kolkata',
        'channels': ['severe'],
    })
    assert created.status_code == 200

    unauthenticated = client.get('/v1/alerts/subscriptions', params={'device_id': first['device_id']})
    assert unauthenticated.status_code == 401

    cross = client.get('/v1/alerts/subscriptions', headers=_auth_headers(first['device_id'], second['device_token']))
    assert cross.status_code == 401

    other_list = client.get('/v1/alerts/subscriptions', headers=_auth_headers(second['device_id'], second['device_token']))
    assert other_list.status_code == 200
    assert other_list.json()['subscriptions'] == []

    own = client.get('/v1/alerts/subscriptions', headers=_auth_headers(first['device_id'], first['device_token']))
    assert len(own.json()['subscriptions']) == 1
    assert own.json()['subscriptions'][0]['latitude'] == 19.07
