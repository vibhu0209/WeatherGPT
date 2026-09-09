from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

_STORE = Path(__file__).resolve().parents[1] / "data" / "alert_rules.json"
_LOCK = Lock()


def _load() -> dict:
    if not _STORE.exists():
        return {"rules": []}
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {"rules": []}


def _save(payload: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_rule(*, channels: list[str], enabled: bool, location_name: str, latitude: float, longitude: float) -> dict:
    with _LOCK:
        payload = _load()
        rules = [rule for rule in payload.get("rules", []) if not (
            abs(float(rule.get("latitude", 0)) - latitude) < 1e-6
            and abs(float(rule.get("longitude", 0)) - longitude) < 1e-6
        )]
        entry = {
            "location_name": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "channels": channels,
            "enabled": enabled,
        }
        rules.append(entry)
        payload["rules"] = rules[-200:]
        _save(payload)
        return entry
