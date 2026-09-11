"""Optional persistent device and subscription storage.

Local development and pytest keep an in-memory store. Set WEATHERGPT_STORE=sqlite
(or Settings.store_backend=sqlite) for a file that survives process restarts.
Redis/PostgreSQL can implement the same DeviceStore protocol later.
"""
from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import Settings


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


class DeviceStore(ABC):
    @abstractmethod
    def get_device(self, device_id: str) -> DeviceRecord | None: ...
    @abstractmethod
    def put_device(self, record: DeviceRecord) -> None: ...
    @abstractmethod
    def get_subscription(self, subscription_id: str) -> AlertSubscription | None: ...
    @abstractmethod
    def put_subscription(self, subscription: AlertSubscription) -> None: ...
    @abstractmethod
    def delete_subscription(self, subscription_id: str) -> None: ...
    @abstractmethod
    def list_subscriptions(self, device_id: str | None = None) -> list[AlertSubscription]: ...
    @abstractmethod
    def clear(self) -> None: ...


class MemoryDeviceStore(DeviceStore):
    def __init__(self):
        self.devices: dict[str, DeviceRecord] = {}
        self.subscriptions: dict[str, AlertSubscription] = {}

    def get_device(self, device_id: str) -> DeviceRecord | None:
        return self.devices.get(device_id)

    def put_device(self, record: DeviceRecord) -> None:
        self.devices[record.device_id] = record

    def get_subscription(self, subscription_id: str) -> AlertSubscription | None:
        return self.subscriptions.get(subscription_id)

    def put_subscription(self, subscription: AlertSubscription) -> None:
        self.subscriptions[subscription.id] = subscription

    def delete_subscription(self, subscription_id: str) -> None:
        self.subscriptions.pop(subscription_id, None)

    def list_subscriptions(self, device_id: str | None = None) -> list[AlertSubscription]:
        items = list(self.subscriptions.values())
        if device_id is None:
            return items
        return [item for item in items if item.device_id == device_id]

    def clear(self) -> None:
        self.devices.clear()
        self.subscriptions.clear()


class SqliteDeviceStore(DeviceStore):
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    timezone TEXT NOT NULL,
                    channels TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def get_device(self, device_id: str) -> DeviceRecord | None:
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM devices WHERE device_id=?', (device_id,)).fetchone()
        if row is None:
            return None
        return DeviceRecord(device_id=row['device_id'], secret_hash=row['secret_hash'],
            created_at=row['created_at'], revoked=bool(row['revoked']))

    def put_device(self, record: DeviceRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO devices(device_id,secret_hash,created_at,revoked) VALUES(?,?,?,?)',
                (record.device_id, record.secret_hash, record.created_at, int(record.revoked)),
            )

    def get_subscription(self, subscription_id: str) -> AlertSubscription | None:
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM subscriptions WHERE id=?', (subscription_id,)).fetchone()
        return None if row is None else self._row_to_sub(row)

    def put_subscription(self, subscription: AlertSubscription) -> None:
        with self._connect() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO subscriptions(id,device_id,latitude,longitude,timezone,channels,created_at) VALUES(?,?,?,?,?,?,?)',
                (subscription.id, subscription.device_id, subscription.latitude, subscription.longitude,
                 subscription.timezone, ','.join(subscription.channels), subscription.created_at),
            )

    def delete_subscription(self, subscription_id: str) -> None:
        with self._connect() as conn:
            conn.execute('DELETE FROM subscriptions WHERE id=?', (subscription_id,))

    def list_subscriptions(self, device_id: str | None = None) -> list[AlertSubscription]:
        with self._connect() as conn:
            if device_id is None:
                rows = conn.execute('SELECT * FROM subscriptions').fetchall()
            else:
                rows = conn.execute('SELECT * FROM subscriptions WHERE device_id=?', (device_id,)).fetchall()
        return [self._row_to_sub(row) for row in rows]

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute('DELETE FROM subscriptions')
            conn.execute('DELETE FROM devices')

    @staticmethod
    def _row_to_sub(row: sqlite3.Row) -> AlertSubscription:
        return AlertSubscription(
            id=row['id'], device_id=row['device_id'], latitude=row['latitude'], longitude=row['longitude'],
            timezone=row['timezone'], channels=[item for item in row['channels'].split(',') if item],
            created_at=row['created_at'],
        )


_store: DeviceStore | None = None


def reset_store_for_tests() -> MemoryDeviceStore:
    global _store
    _store = MemoryDeviceStore()
    return _store


def get_store() -> DeviceStore:
    global _store
    if _store is None:
        kind = (os.getenv('WEATHERGPT_STORE') or Settings().store_backend or 'memory').strip().lower()
        if kind == 'sqlite':
            path = os.getenv('WEATHERGPT_STORE_PATH') or Settings().store_path or str(
                Path(__file__).resolve().parents[1] / 'data' / 'devices.sqlite'
            )
            _store = SqliteDeviceStore(path)
        else:
            _store = MemoryDeviceStore()
    return _store
