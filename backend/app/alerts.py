from __future__ import annotations

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import httpx

from .models import Location, Settings


CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def _text(node: ET.Element, path: str) -> str | None:
    value = node.findtext(path, namespaces=CAP_NS)
    return value.strip() if value and value.strip() else None


def _instant(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("CAP timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _inside_polygon(latitude: float, longitude: float, value: str) -> bool:
    points = []
    for pair in value.split():
        lat, lon = pair.split(",", 1)
        points.append((float(lat), float(lon)))
    if len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i, (yi, xi) in enumerate(points):
        yj, xj = points[j]
        if (yi > latitude) != (yj > latitude):
            boundary = (xj - xi) * (latitude - yi) / (yj - yi) + xi
            if longitude < boundary:
                inside = not inside
        j = i
    return inside


def parse_cap(xml: str, location: Location, now: datetime | None = None) -> list[dict]:
    """Parse CAP 1.2 and retain only active alerts whose polygon contains the place."""
    root = ET.fromstring(xml)
    if root.tag.endswith("feed"):
        nodes = [entry.find("cap:alert", CAP_NS) for entry in root]
        nodes = [node for node in nodes if node is not None]
    else:
        nodes = [root]
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    output = []
    for alert in nodes:
        status = _text(alert, "cap:status")
        msg_type = _text(alert, "cap:msgType")
        if status != "Actual" or msg_type in {"Cancel", "Error"}:
            continue
        for info in alert.findall("cap:info", CAP_NS):
            effective = _instant(_text(info, "cap:effective") or _text(alert, "cap:sent"))
            expires = _instant(_text(info, "cap:expires"))
            if effective and current < effective or expires and current >= expires:
                continue
            areas = info.findall("cap:area", CAP_NS)
            polygons = [p.text.strip() for area in areas for p in area.findall("cap:polygon", CAP_NS) if p.text]
            if polygons and not any(_inside_polygon(location.latitude, location.longitude, p) for p in polygons):
                continue
            output.append({
                "id": _text(alert, "cap:identifier") or "unknown",
                "classification": "OFFICIAL_WARNING",
                "sender": _text(alert, "cap:sender"),
                "sent": _text(alert, "cap:sent"),
                "event": _text(info, "cap:event") or "Weather warning",
                "headline": _text(info, "cap:headline") or _text(info, "cap:event") or "Weather warning",
                "description": _text(info, "cap:description"),
                "instruction": _text(info, "cap:instruction"),
                "severity": (_text(info, "cap:severity") or "Unknown").lower(),
                "urgency": (_text(info, "cap:urgency") or "Unknown").lower(),
                "certainty": (_text(info, "cap:certainty") or "Unknown").lower(),
                "effective": effective.isoformat() if effective else None,
                "expires": expires.isoformat() if expires else None,
                "area_descriptions": [_text(area, "cap:areaDesc") for area in areas if _text(area, "cap:areaDesc")],
                "source_format": "CAP_1_2",
            })
    severity_order = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3, "unknown": 4}
    return sorted(output, key=lambda item: severity_order.get(item["severity"], 4))


class AlertService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    async def official(self, location: Location) -> dict:
        if not self.settings.cap_alert_url:
            return {"status": "unavailable", "alerts": [], "message": "Official warning data is not connected. This does not mean there are no warnings."}
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                response = await client.get(self.settings.cap_alert_url)
                response.raise_for_status()
            return {"status": "available", "alerts": parse_cap(response.text, location), "message": None}
        except (httpx.HTTPError, ET.ParseError, ValueError):
            return {"status": "unavailable", "alerts": [], "message": "Official warning data could not be checked. This does not mean there are no warnings."}


alert_service = AlertService()
