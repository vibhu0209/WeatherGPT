"""In-memory alert subscription store for the SIH prototype. Replace with PostgreSQL in production."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class AlertSubscription:
    id: str
    device_id: str
    latitude: float
    longitude: float
    timezone: str
    channels: list[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_store: dict[str, AlertSubscription] = {}


def create(device_id: str, latitude: float, longitude: float, timezone: str, channels: list[str]) -> AlertSubscription:
    subscription = AlertSubscription(
        id=str(uuid4()),
        device_id=device_id[:80],
        latitude=latitude,
        longitude=longitude,
        timezone=timezone[:64],
        channels=[channel for channel in channels if channel in {'severe', 'rain', 'daily', 'forecast_change'}],
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
