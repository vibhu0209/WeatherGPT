"""Device registration and alert subscription store with ownership tokens.

Default store is in-memory for local SIH demo and pytest. Configure
WEATHERGPT_STORE=sqlite so a backend restart does not drop production
subscriptions. Precise coordinates are stored only for authenticated device
owners and are never listed without a valid device token.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from .persist import AlertSubscription, DeviceRecord, get_store, reset_store_for_tests

MAX_SUBSCRIPTIONS_PER_DEVICE = 5

__all__ = [
    'AlertSubscription', 'DeviceRecord', 'MAX_SUBSCRIPTIONS_PER_DEVICE',
    'authenticate', 'create', 'delete', 'list_for_device', 'register', 'reset_for_tests', 'revoke',
]


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def register(device_id: str | None = None) -> dict:
    """Mint a random device id (unless supplied) and a one-time device token.

    A client-supplied id may only claim an id that is not already registered.
    Re-registering a live id would otherwise let any unauthenticated caller
    rotate another device's token and delete its severe-weather subscriptions.
    """
    store = get_store()
    resolved_id = (device_id or secrets.token_urlsafe(18))[:80]
    if len(resolved_id) < 8:
        raise ValueError("device_id must be at least 8 characters")
    existing = store.get_device(resolved_id)
    if existing is not None and not existing.revoked:
        raise PermissionError("device_id is already registered")
    token = secrets.token_urlsafe(32)
    record = DeviceRecord(
        device_id=resolved_id,
        secret_hash=_hash_secret(token),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.put_device(record)
    for item in store.list_subscriptions(resolved_id):
        store.delete_subscription(item.id)
    return {
        "device_id": resolved_id,
        "device_token": token,
        "registered_at": record.created_at,
        "status": "accepted",
        "token_hint": "Store device_token privately. It is shown only once.",
    }


def authenticate(device_id: str | None, authorization: str | None) -> DeviceRecord:
    if not device_id or len(device_id) < 8:
        raise PermissionError("Device authentication required")
    record = get_store().get_device(device_id)
    if not record or record.revoked:
        raise PermissionError("Unknown or revoked device")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PermissionError("Device authentication required")
    token = authorization.split(" ", 1)[1].strip()
    if not token or not hmac.compare_digest(record.secret_hash, _hash_secret(token)):
        raise PermissionError("Invalid device token")
    return record


def revoke(device_id: str) -> bool:
    store = get_store()
    record = store.get_device(device_id)
    if not record:
        return False
    record.revoked = True
    store.put_device(record)
    for item in store.list_subscriptions(device_id):
        store.delete_subscription(item.id)
    return True


def create(device_id: str, latitude: float, longitude: float, timezone_name: str, channels: list[str]) -> AlertSubscription:
    store = get_store()
    existing = store.list_subscriptions(device_id)
    if len(existing) >= MAX_SUBSCRIPTIONS_PER_DEVICE:
        raise ValueError("Subscription limit reached for this device")
    subscription = AlertSubscription(
        id=str(uuid4()),
        device_id=device_id[:80],
        latitude=latitude,
        longitude=longitude,
        timezone=timezone_name[:64],
        channels=[channel for channel in channels if channel in {"severe", "rain", "daily", "forecast_change"}],
    )
    store.put_subscription(subscription)
    return subscription


def list_for_device(device_id: str) -> list[AlertSubscription]:
    return get_store().list_subscriptions(device_id)


def delete(subscription_id: str, device_id: str) -> bool:
    store = get_store()
    existing = store.get_subscription(subscription_id)
    if not existing or existing.device_id != device_id:
        return False
    store.delete_subscription(subscription_id)
    return True


def reset_for_tests() -> None:
    reset_store_for_tests()
