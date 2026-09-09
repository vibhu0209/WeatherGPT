"""Shared security, privacy and abuse-prevention helpers."""
from __future__ import annotations

import math
import re
from collections import OrderedDict, deque
from time import monotonic
from urllib.parse import urlparse
from ipaddress import ip_address

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_COORD_PATTERN = re.compile(
    r"(?i)(?:\b(?:lat(?:itude)?|lon(?:gitude)?|coords?)\b\s*[:=]?\s*)?"
    r"[-+]?\d{1,3}\.\d{2,}\s*[,/]\s*[-+]?\d{1,3}\.\d{2,}"
    r"|(?:\b(?:lat(?:itude)?|lon(?:gitude)?)\b\s*[:=]\s*[-+]?\d+(?:\.\d+)?)"
)
_SECRET_QUERY_KEYS = {"key", "appid", "api_key", "apikey", "token", "access_token", "authorization"}
_PRIVATE_HOST_FRAGMENTS = ("localhost", "metadata.google", "169.254.", "metadata.azure")


def geohash_encode(latitude: float, longitude: float, precision: int = 5) -> str:
    """Encode coordinates to a geohash. Precision 5 is roughly a 5 km cell."""
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Coordinates out of range")
    if precision < 1 or precision > 12:
        raise ValueError("Unsupported geohash precision")
    lat_min, lat_max = -90.0, 90.0
    lon_min, lon_max = -180.0, 180.0
    bits = []
    lon_bit = True
    while len(bits) < precision * 5:
        if lon_bit:
            mid = (lon_min + lon_max) / 2
            if longitude >= mid:
                bits.append(1)
                lon_min = mid
            else:
                bits.append(0)
                lon_max = mid
        else:
            mid = (lat_min + lat_max) / 2
            if latitude >= mid:
                bits.append(1)
                lat_min = mid
            else:
                bits.append(0)
                lat_max = mid
        lon_bit = not lon_bit
    chars = []
    for index in range(0, len(bits), 5):
        value = 0
        for bit in bits[index:index + 5]:
            value = (value << 1) | bit
        chars.append(_BASE32[value])
    return "".join(chars)


def weather_cache_key(latitude: float, longitude: float, timezone_name: str, precision: int = 5) -> tuple:
    return (geohash_encode(latitude, longitude, precision), timezone_name)


def redact_coordinates(text: str) -> str:
    return _COORD_PATTERN.sub("[location]", text or "")


def public_location(location) -> dict:
    """Client-facing location without precise GPS when only a label is needed for context."""
    payload = location.model_dump() if hasattr(location, "model_dump") else dict(location)
    return {
        "name": payload.get("name"),
        "timezone": payload.get("timezone"),
        "latitude": None,
        "longitude": None,
        "precision": "label_only",
    }


def sanitize_gemini_question(question: str) -> str:
    return redact_coordinates(question)[:1000]


def redact_secrets(text: str) -> str:
    if not text:
        return text
    redacted = text
    for key in _SECRET_QUERY_KEYS:
        redacted = re.sub(rf"(?i)([?&]{key}=)[^&\s]+", rf"\1[REDACTED]", redacted)
    redacted = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", redacted)
    return redact_coordinates(redacted)


def assert_https_allowlisted(url: str, allowed_hosts: set[str] | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("External URL must use https")
    if parsed.username or parsed.password:
        raise ValueError("External URL must not embed credentials")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("External URL host is required")
    if any(fragment in host for fragment in _PRIVATE_HOST_FRAGMENTS):
        raise ValueError("External URL host is not permitted")
    try:
        address = ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("External URL host is not permitted")
    except ValueError as error:
        if "not permitted" in str(error):
            raise
    if allowed_hosts is not None and host not in {item.lower() for item in allowed_hosts}:
        raise ValueError("External URL host is not allowlisted")
    return host


def finite_coordinate(value: float, minimum: float, maximum: float) -> float:
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError("Coordinate out of range")
    return value


class SlidingWindowLimiter:
    """Simple per-key rate limiter with bounded memory."""

    def __init__(self, limit: int, window_seconds: float = 60.0, max_keys: int = 4096):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = monotonic()
        queue = self._hits.get(key)
        if queue is None:
            while len(self._hits) >= self.max_keys:
                self._hits.popitem(last=False)
            queue = deque()
            self._hits[key] = queue
        else:
            self._hits.move_to_end(key)
        while queue and queue[0] < now - self.window_seconds:
            queue.popleft()
        if len(queue) >= self.limit:
            return False
        queue.append(now)
        return True
