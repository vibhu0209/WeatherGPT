from pathlib import Path

from app.persist import SqliteDeviceStore, DeviceRecord, AlertSubscription
from app import subscriptions


def test_sqlite_store_survives_reopen(tmp_path: Path):
    path = str(tmp_path / 'devices.sqlite')
    first = SqliteDeviceStore(path)
    first.put_device(DeviceRecord(device_id='device-abc12', secret_hash='abc', created_at='2026-09-11T00:00:00+00:00'))
    first.put_subscription(AlertSubscription(
        id='sub-1', device_id='device-abc12', latitude=19.07, longitude=72.87,
        timezone='Asia/Kolkata', channels=['severe'],
    ))
    second = SqliteDeviceStore(path)
    assert second.get_device('device-abc12') is not None
    listed = second.list_subscriptions('device-abc12')
    assert len(listed) == 1
    assert listed[0].channels == ['severe']


def test_memory_store_is_the_test_default():
    subscriptions.reset_for_tests()
    first = subscriptions.register()
    subscriptions.reset_for_tests()
    try:
        subscriptions.authenticate(first['device_id'], f"Bearer {first['device_token']}")
        assert False, 'memory store should be empty after reset'
    except PermissionError:
        pass
