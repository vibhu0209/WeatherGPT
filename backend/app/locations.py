from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass

import httpx

from .models import Location, Settings

_log = logging.getLogger('weathergpt.locations')

POPULAR_INDIA = [
    Location(name='Delhi', latitude=28.6139, longitude=77.2090, timezone='Asia/Kolkata', provider='local'),
    Location(name='Mumbai', latitude=19.0760, longitude=72.8777, timezone='Asia/Kolkata', provider='local'),
    Location(name='Bengaluru', latitude=12.9716, longitude=77.5946, timezone='Asia/Kolkata', provider='local'),
    Location(name='Chennai', latitude=13.0827, longitude=80.2707, timezone='Asia/Kolkata', provider='local'),
    Location(name='Kolkata', latitude=22.5726, longitude=88.3639, timezone='Asia/Kolkata', provider='local'),
    Location(name='Hyderabad', latitude=17.3850, longitude=78.4867, timezone='Asia/Kolkata', provider='local'),
    Location(name='Pune', latitude=18.5204, longitude=73.8567, timezone='Asia/Kolkata', provider='local'),
    Location(name='Ahmedabad', latitude=23.0225, longitude=72.5714, timezone='Asia/Kolkata', provider='local'),
    Location(name='Jaipur', latitude=26.9124, longitude=75.7873, timezone='Asia/Kolkata', provider='local'),
    Location(name='Lucknow', latitude=26.8467, longitude=80.9462, timezone='Asia/Kolkata', provider='local'),
    Location(name='Patna', latitude=25.5941, longitude=85.1376, timezone='Asia/Kolkata', provider='local'),
    Location(name='Bhopal', latitude=23.2599, longitude=77.4126, timezone='Asia/Kolkata', provider='local'),
    Location(name='Bhubaneswar', latitude=20.2961, longitude=85.8245, timezone='Asia/Kolkata', provider='local'),
    Location(name='Guwahati', latitude=26.1445, longitude=91.7362, timezone='Asia/Kolkata', provider='local'),
    Location(name='Kochi', latitude=9.9312, longitude=76.2673, timezone='Asia/Kolkata', provider='local'),
]

_SEARCH_CACHE_TTL_S = 120.0
_SEARCH_CACHE_MAX = 64
_GOOGLE_MAX_CALLS_PER_MINUTE = 20
_GOOGLE_COOLDOWN_S = 60.0
_GOOGLE_BILLING_COOLDOWN_S = 24 * 60 * 60
_MAX_RESULTS = 8
_NEAREST_CITY_MAX_KM = 75.0
_GENERIC_GPS_NAMES = {
    'current location',
    'my location',
    'device location',
    'gps',
    'here',
}


@dataclass
class SearchMeta:
    provider: str = ''
    fallback_used: bool = False
    result_count: int = 0
    latency_ms: int = 0
    cached: bool = False


def google_places_configured(settings: Settings | None = None) -> bool:
    settings = settings or Settings()
    return bool((settings.google_places_api_key or settings.google_maps_api_key or '').strip())


def google_places_enabled(settings: Settings | None = None) -> bool:
    settings = settings or Settings()
    return bool(settings.google_places_enabled)


def places_api_key(settings: Settings) -> str:
    return (settings.google_places_api_key or settings.google_maps_api_key or '').strip()


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def _nearest_popular_label(latitude: float, longitude: float) -> str | None:
    best: tuple[float, Location] | None = None
    for place in POPULAR_INDIA:
        distance = _haversine_km(latitude, longitude, place.latitude, place.longitude)
        if best is None or distance < best[0]:
            best = (distance, place)
    if best is None or best[0] > _NEAREST_CITY_MAX_KM:
        return None
    return best[1].name


def _valid_coords(latitude: float, longitude: float) -> bool:
    return -90 <= latitude <= 90 and -180 <= longitude <= 180 and abs(latitude) + abs(longitude) > 0


def _dedupe(places: list[Location]) -> list[Location]:
    seen: set[tuple[str, float, float]] = set()
    unique: list[Location] = []
    for place in places:
        key = (place.name.casefold(), round(place.latitude, 4), round(place.longitude, 4))
        if key in seen:
            continue
        seen.add(key)
        unique.append(place)
    return unique[:_MAX_RESULTS]


def _popular_matches(query: str) -> list[Location]:
    q = query.strip().lower()
    matches = [place for place in POPULAR_INDIA if q in place.name.lower()]
    return _dedupe(matches)


class LocationSearchProvider(ABC):
    name: str = 'provider'

    @abstractmethod
    async def search(self, client: httpx.AsyncClient, query: str, language: str) -> list[Location]:
        raise NotImplementedError


class LocalCityFallbackProvider(LocationSearchProvider):
    name = 'local'

    async def search(self, client: httpx.AsyncClient, query: str, language: str) -> list[Location]:
        return _popular_matches(query)


class OpenMeteoGeocodingProvider(LocationSearchProvider):
    name = 'open-meteo'

    async def search(self, client: httpx.AsyncClient, query: str, language: str) -> list[Location]:
        response = await client.get(
            'https://geocoding-api.open-meteo.com/v1/search',
            params={'name': query, 'count': _MAX_RESULTS, 'language': language, 'countryCode': 'IN'},
        )
        response.raise_for_status()
        places: list[Location] = []
        for row in response.json().get('results') or []:
            try:
                latitude = float(row['latitude'])
                longitude = float(row['longitude'])
            except (KeyError, TypeError, ValueError):
                continue
            if not _valid_coords(latitude, longitude):
                continue
            label = ', '.join(filter(None, [row.get('name'), row.get('admin1'), row.get('country')]))
            if not label:
                continue
            places.append(Location(
                name=label[:120],
                latitude=latitude,
                longitude=longitude,
                timezone=row.get('timezone') or 'Asia/Kolkata',
                provider=self.name,
            ))
        return _dedupe(places)


class GooglePlacesProvider(LocationSearchProvider):
    name = 'google'

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._calls: deque[float] = deque()
        self._cooldown_until = 0.0
        self._billing_denied = False

    def available(self) -> bool:
        return self._budget_ok()

    def _budget_ok(self) -> bool:
        now = time.monotonic()
        if now < self._cooldown_until:
            return False
        while self._calls and self._calls[0] < now - 60:
            self._calls.popleft()
        return len(self._calls) < _GOOGLE_MAX_CALLS_PER_MINUTE

    def _note_call(self) -> None:
        self._calls.append(time.monotonic())

    def _trip(self, seconds: float = _GOOGLE_COOLDOWN_S, *, billing: bool = False) -> None:
        self._cooldown_until = time.monotonic() + seconds
        if billing:
            self._billing_denied = True

    async def _autocomplete(self, client: httpx.AsyncClient, query: str, *, india_only: bool) -> list[dict]:
        if not self._budget_ok():
            raise RuntimeError('google_budget')
        params = {'input': query, 'key': self.api_key, 'types': 'geocode'}
        if india_only:
            params['components'] = 'country:in'
        self._note_call()
        response = await client.get('https://maps.googleapis.com/maps/api/place/autocomplete/json', params=params)
        if response.status_code == 429:
            self._trip(300)
            raise RuntimeError('google_429')
        if response.status_code in {401, 403}:
            self._trip(_GOOGLE_BILLING_COOLDOWN_S, billing=True)
            raise RuntimeError(f'google_{response.status_code}')
        if response.status_code >= 500:
            self._trip(60)
            raise RuntimeError(f'google_{response.status_code}')
        response.raise_for_status()
        payload = response.json()
        status = payload.get('status')
        if status == 'OVER_QUERY_LIMIT':
            self._trip(300)
            raise RuntimeError('google_429')
        if status == 'REQUEST_DENIED':
            self._trip(_GOOGLE_BILLING_COOLDOWN_S, billing=True)
            detail = str(payload.get('error_message') or 'request_denied').split('.')[0][:80]
            _log.info('google_places denied detail=%s cooldown_s=%s', detail, _GOOGLE_BILLING_COOLDOWN_S)
            raise RuntimeError('google_403')
        if status not in {'OK', 'ZERO_RESULTS'}:
            raise ValueError(status or 'google_places_error')
        return list(payload.get('predictions') or [])

    async def _details(self, client: httpx.AsyncClient, place_id: str, fallback_name: str) -> Location | None:
        if not self._budget_ok():
            return None
        self._note_call()
        response = await client.get(
            'https://maps.googleapis.com/maps/api/place/details/json',
            params={'place_id': place_id, 'fields': 'geometry,name,formatted_address,address_component', 'key': self.api_key},
        )
        if response.status_code == 429:
            self._trip(300)
            return None
        if response.status_code in {401, 403} or response.status_code >= 500:
            return None
        response.raise_for_status()
        payload = response.json()
        if payload.get('status') not in {'OK'}:
            return None
        result = payload.get('result') or {}
        location = ((result.get('geometry') or {}).get('location')) or {}
        try:
            latitude = float(location['lat'])
            longitude = float(location['lng'])
        except (KeyError, TypeError, ValueError):
            return None
        if not _valid_coords(latitude, longitude):
            return None
        name = result.get('formatted_address') or result.get('name') or fallback_name or 'Selected place'
        return Location(
            name=str(name)[:120],
            latitude=latitude,
            longitude=longitude,
            timezone='Asia/Kolkata',
            provider=self.name,
            provider_place_id=place_id[:120],
        )

    async def search(self, client: httpx.AsyncClient, query: str, language: str) -> list[Location]:
        predictions = await self._autocomplete(client, query, india_only=True)
        if not predictions:
            predictions = await self._autocomplete(client, query, india_only=False)
        places: list[Location] = []
        for prediction in predictions[:6]:
            place_id = prediction.get('place_id')
            description = prediction.get('description') or query
            if not place_id:
                continue
            detail = await self._details(client, place_id, description)
            if detail is not None:
                places.append(detail)
                continue
            # Autocomplete sometimes lacks coords; skip incomplete rows rather than inventing them.
        return _dedupe(places)

    async def reverse_geocode(self, client: httpx.AsyncClient, latitude: float, longitude: float) -> str | None:
        if not self._budget_ok():
            return None
        # Round to ~1km so reverse lookups coalesce and avoid logging/storing raw GPS precision.
        rounded_lat = round(latitude, 2)
        rounded_lon = round(longitude, 2)
        self._note_call()
        response = await client.get(
            'https://maps.googleapis.com/maps/api/geocode/json',
            params={'latlng': f'{rounded_lat},{rounded_lon}', 'key': self.api_key, 'result_type': 'locality|administrative_area_level_2|administrative_area_level_1'},
        )
        if response.status_code == 429:
            self._trip(300)
            return None
        if response.status_code in {401, 403} or response.status_code >= 500:
            if response.status_code in {401, 403}:
                self._trip(_GOOGLE_BILLING_COOLDOWN_S, billing=True)
            return None
        response.raise_for_status()
        payload = response.json()
        if payload.get('status') == 'REQUEST_DENIED':
            self._trip(_GOOGLE_BILLING_COOLDOWN_S, billing=True)
            return None
        if payload.get('status') not in {'OK', 'ZERO_RESULTS'}:
            return None
        for row in payload.get('results') or []:
            components = row.get('address_components') or []
            locality = next((c.get('long_name') for c in components if 'locality' in (c.get('types') or [])), None)
            district = next((c.get('long_name') for c in components if 'administrative_area_level_2' in (c.get('types') or [])), None)
            state = next((c.get('long_name') for c in components if 'administrative_area_level_1' in (c.get('types') or [])), None)
            country = next((c.get('long_name') for c in components if 'country' in (c.get('types') or [])), None)
            label = ', '.join(part for part in (locality or district, state, country) if part)
            if label:
                return label[:120]
            formatted = row.get('formatted_address')
            if formatted:
                return str(formatted)[:120]
        return None


async def _nominatim_reverse(client: httpx.AsyncClient, latitude: float, longitude: float) -> str | None:
    """Free OpenStreetMap reverse geocode. No paid Maps billing."""
    rounded_lat = round(latitude, 2)
    rounded_lon = round(longitude, 2)
    response = await client.get(
        'https://nominatim.openstreetmap.org/reverse',
        params={
            'lat': rounded_lat,
            'lon': rounded_lon,
            'format': 'jsonv2',
            'zoom': 12,
            'addressdetails': 1,
        },
        headers={'User-Agent': 'WeatherGPT/1.0 (local weather assistant; contact: local-dev)'},
    )
    if response.status_code >= 400:
        return None
    payload = response.json()
    address = payload.get('address') or {}
    locality = (
        address.get('city')
        or address.get('town')
        or address.get('village')
        or address.get('suburb')
        or address.get('county')
        or address.get('state_district')
    )
    state = address.get('state')
    country = address.get('country')
    label = ', '.join(part for part in (locality, state, country) if part)
    if label:
        return label[:120]
    display = payload.get('display_name')
    return str(display)[:120] if display else None


async def reverse_geocode_label(
    latitude: float,
    longitude: float,
    settings: Settings | None = None,
) -> tuple[str | None, str]:
    """Return (friendly_label, provider). Never raises; never invents coordinates."""
    settings = settings or Settings()
    google = _google(settings)
    if google is not None and google.available():
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                friendly = await google.reverse_geocode(client, latitude, longitude)
            if friendly:
                return friendly, 'google'
        except Exception as error:
            _log.info('reverse_geocode provider=google failed reason=%s', type(error).__name__)
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            friendly = await _nominatim_reverse(client, latitude, longitude)
        if friendly:
            return friendly, 'nominatim'
    except Exception as error:
        _log.info('reverse_geocode provider=nominatim failed reason=%s', type(error).__name__)
    nearest = _nearest_popular_label(latitude, longitude)
    if nearest:
        return nearest, 'local'
    return None, ''


class MapplsPlacesProvider(LocationSearchProvider):
    name = 'mappls'

    def __init__(self, token: str):
        self.token = token

    async def search(self, client: httpx.AsyncClient, query: str, language: str) -> list[Location]:
        auto = await client.get(
            'https://search.mappls.com/search/places/autosuggest/json',
            params={'query': query, 'access_token': self.token},
        )
        auto.raise_for_status()
        payload = auto.json()
        places: list[Location] = []
        for row in (payload.get('suggestedLocations') or payload.get('suggested_locations') or [])[:6]:
            latitude = row.get('latitude') or row.get('lat')
            longitude = row.get('longitude') or row.get('lng') or row.get('lon')
            e_loc = row.get('eLoc') or row.get('placeId')
            name = row.get('placeAddress') or row.get('placeName') or row.get('description') or query
            if latitude is None or longitude is None:
                if not e_loc:
                    continue
                entity = await client.get(
                    f'https://explore.mappls.com/apis/O2O/entity/{e_loc}',
                    params={'access_token': self.token},
                )
                entity.raise_for_status()
                data = entity.json()
                latitude = data.get('latitude')
                longitude = data.get('longitude')
                name = data.get('address') or data.get('name') or name
            try:
                lat_f = float(latitude)
                lon_f = float(longitude)
            except (TypeError, ValueError):
                continue
            if not _valid_coords(lat_f, lon_f):
                continue
            places.append(Location(
                name=str(name)[:120],
                latitude=lat_f,
                longitude=lon_f,
                timezone='Asia/Kolkata',
                provider=self.name,
                provider_place_id=str(e_loc or '')[:120],
            ))
        return _dedupe(places)


class _SearchCache:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, list[Location], SearchMeta]] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [key for key, (expires, _, _) in self._entries.items() if expires <= now]
        for key in expired:
            self._entries.pop(key, None)
        while len(self._entries) > _SEARCH_CACHE_MAX:
            self._entries.pop(next(iter(self._entries)))

    async def get_or_fetch(self, key: str, fetch):
        async with self._lock:
            self._prune()
            cached = self._entries.get(key)
            if cached and cached[0] > time.monotonic():
                places, meta = cached[1], cached[2]
                meta = SearchMeta(
                    provider=meta.provider,
                    fallback_used=meta.fallback_used,
                    result_count=len(places),
                    latency_ms=0,
                    cached=True,
                )
                return [place.model_copy() for place in places], meta
            existing = self._inflight.get(key)
            if existing is not None:
                waiter = existing
            else:
                loop = asyncio.get_running_loop()
                waiter = loop.create_future()
                self._inflight[key] = waiter

                async def _run() -> None:
                    try:
                        result = await fetch()
                        waiter.set_result(result)
                    except Exception as error:
                        waiter.set_exception(error)
                    finally:
                        async with self._lock:
                            self._inflight.pop(key, None)

                asyncio.create_task(_run())
        places, meta = await waiter
        async with self._lock:
            self._entries[key] = (time.monotonic() + _SEARCH_CACHE_TTL_S, [p.model_copy() for p in places], meta)
            self._prune()
        return [place.model_copy() for place in places], meta


_search_cache = _SearchCache()
_google_provider: GooglePlacesProvider | None = None
_google_provider_key = ''


def _google(settings: Settings) -> GooglePlacesProvider | None:
    global _google_provider, _google_provider_key
    if not google_places_enabled(settings):
        return None
    key = places_api_key(settings)
    if not key:
        return None
    if _google_provider is None or _google_provider_key != key:
        _google_provider = GooglePlacesProvider(key)
        _google_provider_key = key
    return _google_provider


def build_search_providers(settings: Settings) -> list[LocationSearchProvider]:
    """Zero-cost first: Mappls (optional) → Open-Meteo → local. Google only when enabled."""
    providers: list[LocationSearchProvider] = []
    if settings.mappls_access_token:
        providers.append(MapplsPlacesProvider(settings.mappls_access_token))
    google = _google(settings)
    if google is not None and google.available():
        providers.append(google)
    providers.append(OpenMeteoGeocodingProvider())
    providers.append(LocalCityFallbackProvider())
    return providers


async def _search_uncached(query: str, language: str, settings: Settings) -> tuple[list[Location], SearchMeta]:
    started = time.monotonic()
    providers = build_search_providers(settings)
    fallback_used = False
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        for index, provider in enumerate(providers):
            try:
                places = await provider.search(client, query, language)
            except Exception as error:
                _log.info(
                    'place_search provider=%s failed reason=%s',
                    provider.name,
                    type(error).__name__,
                )
                fallback_used = True
                continue
            if places:
                places = _dedupe(places)
                latency_ms = int((time.monotonic() - started) * 1000)
                meta = SearchMeta(
                    provider=provider.name,
                    fallback_used=fallback_used or index > 0,
                    result_count=len(places),
                    latency_ms=latency_ms,
                    cached=False,
                )
                _log.info(
                    'place_search query_len=%s provider=%s count=%s latency_ms=%s fallback=%s',
                    len(query),
                    meta.provider,
                    meta.result_count,
                    meta.latency_ms,
                    meta.fallback_used,
                )
                return places, meta
            fallback_used = True
    latency_ms = int((time.monotonic() - started) * 1000)
    return [], SearchMeta(provider='none', fallback_used=True, result_count=0, latency_ms=latency_ms, cached=False)


async def search_places(
    query: str,
    language: str = 'en',
    settings: Settings | None = None,
) -> list[Location]:
    places, _ = await search_places_with_meta(query, language, settings)
    return places


async def search_places_with_meta(
    query: str,
    language: str = 'en',
    settings: Settings | None = None,
) -> tuple[list[Location], SearchMeta]:
    settings = settings or Settings()
    q = query.strip()
    if len(q) < 2:
        return [], SearchMeta(provider='none', result_count=0)
    cache_key = f'{language.casefold()}|{q.casefold()}'

    async def fetch():
        return await _search_uncached(q, language, settings)

    return await _search_cache.get_or_fetch(cache_key, fetch)


async def resolve_timezone(latitude: float, longitude: float, name: str, settings: Settings | None = None) -> Location:
    """Resolve timezone and optionally a friendly GPS label. Never invents coordinates."""
    settings = settings or Settings()
    label = (name or '').strip() or 'Current location'
    provider = ''
    if label.casefold() in _GENERIC_GPS_NAMES:
        friendly, source = await reverse_geocode_label(latitude, longitude, settings)
        if friendly:
            label = friendly
            provider = source
            _log.info('reverse_geocode provider=%s label_len=%s', source, len(label))
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.get(
                'https://api.open-meteo.com/v1/forecast',
                params={
                    'latitude': latitude,
                    'longitude': longitude,
                    'timezone': 'auto',
                    'forecast_days': 1,
                    'hourly': 'temperature_2m',
                },
            )
            response.raise_for_status()
            timezone_name = response.json().get('timezone') or 'Asia/Kolkata'
            return Location(
                name=label[:120],
                latitude=latitude,
                longitude=longitude,
                timezone=timezone_name,
                provider=provider or 'open-meteo',
            )
    except Exception:
        # India-first default so onboarding never hangs on reverse-geocode failures.
        return Location(
            name=label[:120],
            latitude=latitude,
            longitude=longitude,
            timezone='Asia/Kolkata',
            provider=provider or 'local',
        )


# Back-compat aliases used by older tests / imports.
async def _open_meteo(client: httpx.AsyncClient, query: str, language: str) -> list[Location]:
    return await OpenMeteoGeocodingProvider().search(client, query, language)


async def _google_places(client: httpx.AsyncClient, query: str, api_key: str) -> list[Location]:
    return await GooglePlacesProvider(api_key).search(client, query, language='en')


async def _mappls_places(client: httpx.AsyncClient, query: str, token: str) -> list[Location]:
    return await MapplsPlacesProvider(token).search(client, query, language='en')
