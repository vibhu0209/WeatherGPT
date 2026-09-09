"""Device registration and alert subscription store with ownership tokens.

In-memory for the SIH prototype. Replace with PostgreSQL + hashed tokens in production.
Precise coordinates are stored only for authenticated device owners and are never listed
without a valid device token.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

MAX_SUBSCRIPTIONS_PER_DEVICE = 5


@dataclass
class DeviceRecord:
    device_id: str
    secret_hash: str
    created_at: str
    revoked: bool = False


@dataclass
class AlertSubscription:
    id: str
    device_id: str
    latitude: float
    longitude: float
    timezone: str
    channels: list[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_devices: dict[str, DeviceRecord] = {}
_store: dict[str, AlertSubscription] = {}


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def register(device_id: str | None = None) -> dict:
    """Mint a random device id (unless supplied) and a one-time device token."""
    resolved_id = (device_id or secrets.token_urlsafe(18))[:80]
    if len(resolved_id) < 8:
        raise ValueError("device_id must be at least 8 characters")
    token = secrets.token_urlsafe(32)
    _devices[resolved_id] = DeviceRecord(
        device_id=resolved_id,
        secret_hash=_hash_secret(token),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    # Drop any prior subscriptions if the device is re-registered.
    for subscription_id, item in list(_store.items()):
        if item.device_id == resolved_id:
            del _store[subscription_id]
    return {
        "device_id": resolved_id,
        "device_token": token,
        "registered_at": _devices[resolved_id].created_at,
        "status": "accepted",
        "token_hint": "Store device_token privately. It is shown only once.",
    }


def authenticate(device_id: str | None, authorization: str | None) -> DeviceRecord:
    if not device_id or len(device_id) < 8:
        raise PermissionError("Device authentication required")
    record = _devices.get(device_id)
    if not record or record.revoked:
        raise PermissionError("Unknown or revoked device")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PermissionError("Device authentication required")
    token = authorization.split(" ", 1)[1].strip()
    if not token or not hmac.compare_digest(record.secret_hash, _hash_secret(token)):
        raise PermissionError("Invalid device token")
    return record


def revoke(device_id: str) -> bool:
    record = _devices.get(device_id)
    if not record:
        return False
    record.revoked = True
    for subscription_id, item in list(_store.items()):
        if item.device_id == device_id:
            del _store[subscription_id]
    return True


def create(device_id: str, latitude: float, longitude: float, timezone_name: str, channels: list[str]) -> AlertSubscription:
    existing = list_for_device(device_id)
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
    _store[subscription.id] = subscription
    return subscription


def list_for_device(device_id: str) -> list[AlertSubscription]:
    return [item for item in _store.values() if item.device_id == device_id]


def delete(subscription_id: str, device_id: str) -> bool:
    existing = _store.get(subscription_id)
    if not existing or existing.device_id != device_id:
        return False
    del _store[subscription_id]
    return True


def reset_for_tests() -> None:
    _devices.clear()
    _store.clear()
