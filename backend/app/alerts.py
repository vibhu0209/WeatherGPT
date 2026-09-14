from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from .cache import CacheBackend, MemoryCacheBackend
from .metrics import metrics
from .models import Location, Settings
from .security import assert_https_allowlisted

audit_log = logging.getLogger('weathergpt.alerts')


def _response_size(response) -> int:
    content = getattr(response, 'content', None)
    if content is not None:
        return len(content)
    text = getattr(response, 'text', '') or ''
    return len(text.encode('utf-8'))

# Official warnings are safety critical, so the window is short. It only has to
# stop every request for the same area from re-fetching the authority feed.
OFFICIAL_CACHE_TTL_SECONDS = 120
OFFICIAL_FAILURE_TTL_SECONDS = 30
MAX_CAP_BYTES = 1_000_000


class CapFeedUnavailable(ValueError):
    """Raised when a recent authority-feed failure is still cached."""


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


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _inside_circle(latitude: float, longitude: float, value: str) -> bool:
    """CAP circle is 'lat,lon radius' with radius in kilometres."""
    try:
        coords, radius_raw = value.strip().rsplit(None, 1)
        lat_s, lon_s = coords.split(",", 1)
        centre_lat, centre_lon, radius_km = float(lat_s), float(lon_s), float(radius_raw)
    except (TypeError, ValueError):
        return False
    if radius_km < 0:
        return False
    return _haversine_km(latitude, longitude, centre_lat, centre_lon) <= radius_km


def _tokens(text: str) -> set[str]:
    return {part for part in re.findall(r'[\w\u0900-\u097F]+', (text or '').lower()) if len(part) >= 3}


def _area_desc_matches(location_name: str, descriptions: list[str]) -> bool:
    place_tokens = _tokens(location_name)
    if not place_tokens:
        return False
    for desc in descriptions:
        desc_tokens = _tokens(desc)
        if place_tokens & desc_tokens:
            return True
        lowered = (desc or '').lower()
        name = (location_name or '').strip().lower()
        if name and name in lowered:
            return True
    return False


def _area_match(location: Location, areas: list[ET.Element]) -> tuple[bool, str, bool]:
    """Return (applies, match_mode, uncertain).

    Prefer geometry (polygon/circle). Fall back to areaDesc / geocode honesty flags —
    never silently treat a missing polygon as “no warning for this place.”
    """
    polygons = [p.text.strip() for area in areas for p in area.findall('cap:polygon', CAP_NS) if p.text and p.text.strip()]
    circles = [c.text.strip() for area in areas for c in area.findall('cap:circle', CAP_NS) if c.text and c.text.strip()]
    geocodes = [g.text.strip() for area in areas for g in area.findall('cap:geocode', CAP_NS) if g.text and g.text.strip()]
    # Also accept nested value forms: <geocode><valueName/><value/>
    for area in areas:
        for geo in area.findall('cap:geocode', CAP_NS):
            value = _text(geo, 'cap:value')
            if value:
                geocodes.append(value)
    descriptions = [_text(area, 'cap:areaDesc') for area in areas if _text(area, 'cap:areaDesc')]

    if polygons:
        if any(_inside_polygon(location.latitude, location.longitude, poly) for poly in polygons):
            return True, 'polygon', False
        if circles and any(_inside_circle(location.latitude, location.longitude, circle) for circle in circles):
            return True, 'circle', False
        return False, 'polygon_miss', False
    if circles:
        if any(_inside_circle(location.latitude, location.longitude, circle) for circle in circles):
            return True, 'circle', False
        return False, 'circle_miss', False
    if descriptions and _area_desc_matches(location.name, descriptions):
        return True, 'area_desc', True
    if geocodes:
        # No published district codebook wired yet — surface with honesty, do not invent fit.
        return True, 'geocode_unverified', True
    if not polygons and not circles and not geocodes and not descriptions:
        return True, 'unconstrained', True
    return False, 'no_match', True


def parse_cap(xml: str, location: Location, now: datetime | None = None) -> list[dict]:
    """Parse CAP 1.2 and retain active alerts that apply to the place (geometry or honest fallback)."""
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
            applies, match_mode, uncertain = _area_match(location, areas)
            if not applies:
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
                "area_match": match_mode,
                "area_match_uncertain": uncertain,
                "source_format": "CAP_1_2",
            })
    severity_order = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3, "unknown": 4}
    return sorted(output, key=lambda item: severity_order.get(item["severity"], 4))


def _rss_or_atom_links(xml: str) -> list[str]:
    """Extract CAP document links from an RSS/Atom index feed."""
    root = ET.fromstring(xml)
    tag = root.tag.lower()
    links: list[str] = []
    if tag.endswith("rss") or tag.endswith("rdf"):
        for item in root.findall("./channel/item"):
            link = (item.findtext("link") or "").strip()
            if link:
                links.append(link)
    elif tag.endswith("feed"):
        for entry in root:
            if not entry.tag.endswith("entry"):
                continue
            href = ""
            for node in entry:
                if node.tag.endswith("link"):
                    href = (node.get("href") or (node.text or "")).strip()
                    if href:
                        break
            if href:
                links.append(href)
    return links


class AlertService:
    def __init__(self, settings: Settings | None = None, max_cap_documents: int = 15,
                 cache: CacheBackend | None = None):
        self.settings = settings or Settings()
        self.max_cap_documents = max_cap_documents
        self.cache = cache or MemoryCacheBackend(max_entries=512)
        self._inflight: dict[str, asyncio.Future] = {}

    def _allowed_hosts(self) -> set[str] | None:
        configured = {host.strip().lower() for host in (self.settings.cap_alert_allowed_hosts or '').split(',') if host.strip()}
        if configured:
            return configured
        if self.settings.cap_alert_url:
            host = urlparse(self.settings.cap_alert_url).hostname
            return {host.lower()} if host else set()
        return set()

    async def _fetch_cap_documents(self, client: httpx.AsyncClient, index_xml: str) -> list[str]:
        allowed = self._allowed_hosts()
        links = _rss_or_atom_links(index_xml)
        if not links:
            return [index_xml]
        sem = asyncio.Semaphore(4)
        async def one(link: str) -> str:
            assert_https_allowlisted(link, allowed)
            async with sem:
                response = await client.get(link)
                response.raise_for_status()
            if _response_size(response) > MAX_CAP_BYTES:
                raise ValueError("CAP document too large")
            return response.text
        return await asyncio.gather(*(one(link) for link in links[: self.max_cap_documents]))

    async def _documents(self) -> list[str]:
        """Fetch the authority feed once per window and share it across requests.

        The documents are location independent, so caching them saves the
        network round trips while each caller still runs the exact per-location
        polygon and lifecycle filter in ``parse_cap``.
        """
        key = f'official_documents:{self.settings.cap_alert_url}'
        cached = self.cache.get(key)
        if cached is not None:
            if cached.get('error'):
                audit_log.info('official_alerts_cached_failure')
                raise CapFeedUnavailable(cached['error'])
            audit_log.info('official_alerts_cache_hit documents=%s', len(cached['documents']))
            metrics.inc('official_cache_hit')
            return cached['documents']
        existing = self._inflight.get(key)
        if existing is not None:
            audit_log.info('official_alerts_coalesce')
            return await asyncio.shield(existing)
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        # Without a waiter the failure is reported by `raise` below, so mark the
        # future's exception retrieved to avoid a spurious asyncio warning.
        future.add_done_callback(lambda done: done.cancelled() or done.exception())
        self._inflight[key] = future
        try:
            assert_https_allowlisted(self.settings.cap_alert_url, self._allowed_hosts())
            async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
                response = await client.get(self.settings.cap_alert_url)
                response.raise_for_status()
                if _response_size(response) > MAX_CAP_BYTES:
                    raise ValueError("CAP document too large")
                documents = await self._fetch_cap_documents(client, response.text)
            self.cache.set(key, {'documents': documents}, ttl_seconds=OFFICIAL_CACHE_TTL_SECONDS)
            audit_log.info('official_alerts_cache_miss documents=%s', len(documents))
            metrics.inc('official_cache_miss')
            if not future.done():
                future.set_result(documents)
            return documents
        except BaseException as error:
            # Briefly remember an outage so a down authority feed is not hammered.
            # Callers still report "unavailable", never "no warnings".
            self.cache.set(key, {'error': type(error).__name__}, ttl_seconds=OFFICIAL_FAILURE_TTL_SECONDS)
            if not future.done():
                future.set_exception(error)
            raise
        finally:
            self._inflight.pop(key, None)

    async def official(self, location: Location) -> dict:
        if not self.settings.cap_alert_url:
            return {"status": "unavailable", "alerts": [], "message": "Official warning data is not connected. This does not mean there are no warnings."}
        try:
            documents = await self._documents()
            alerts: list[dict] = []
            seen: set[str] = set()
            for document in documents:
                for alert in parse_cap(document, location):
                    if alert["id"] in seen:
                        continue
                    seen.add(alert["id"])
                    alerts.append(alert)
            severity_order = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3, "unknown": 4}
            alerts.sort(key=lambda item: severity_order.get(item["severity"], 4))
            return {"status": "available", "alerts": alerts, "message": None}
        except (httpx.HTTPError, ET.ParseError, ValueError):
            return {"status": "unavailable", "alerts": [], "message": "Official warning data could not be checked. This does not mean there are no warnings."}


alert_service = AlertService()
