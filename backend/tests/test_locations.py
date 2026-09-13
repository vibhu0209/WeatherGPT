import asyncio
import json

import httpx
import pytest

from app.locations import (
    GooglePlacesProvider,
    LocalCityFallbackProvider,
    OpenMeteoGeocodingProvider,
    _google,
    _popular_matches,
    _search_cache,
    build_search_providers,
    google_places_configured,
    google_places_enabled,
    resolve_timezone,
    search_places,
    search_places_with_meta,
)
from app.models import Settings


def _settings(**kwargs) -> Settings:
    base = dict(
        google_places_api_key='',
        google_maps_api_key='',
        google_places_enabled=False,
        mappls_access_token='',
    )
    base.update(kwargs)
    return Settings(**base)


@pytest.fixture(autouse=True)
def clear_place_cache():
    _search_cache._entries.clear()
    _search_cache._inflight.clear()
    # Reset shared Google provider between tests.
    import app.locations as locations_mod
    locations_mod._google_provider = None
    locations_mod._google_provider_key = ''
    yield
    _search_cache._entries.clear()
    _search_cache._inflight.clear()
    locations_mod._google_provider = None
    locations_mod._google_provider_key = ''


@pytest.mark.asyncio
async def test_search_falls_back_to_popular_india_cities():
    places = await search_places('Del', 'en', _settings())
    assert places
    assert any('Delhi' in place.name for place in places)
    assert all(place.provider in {'local', 'open-meteo', ''} for place in places)


def test_popular_matches_are_india_first():
    assert [p.name for p in _popular_matches('mum')] == ['Mumbai']


def test_google_places_flags():
    assert google_places_configured(_settings()) is False
    assert google_places_enabled(_settings()) is False
    assert google_places_configured(_settings(google_places_api_key='test')) is True
    assert google_places_enabled(_settings(google_places_enabled=True)) is True
    assert google_places_configured(_settings(google_maps_api_key='maps')) is True


def test_google_disabled_skips_provider_even_with_key():
    providers = build_search_providers(_settings(google_places_api_key='k', google_places_enabled=False))
    assert [p.name for p in providers] == ['open-meteo', 'local']
    assert _google(_settings(google_places_api_key='k', google_places_enabled=False)) is None


def test_google_enabled_inserts_after_mappls():
    providers = build_search_providers(_settings(
        google_places_api_key='k',
        google_places_enabled=True,
        mappls_access_token='token',
    ))
    assert [p.name for p in providers] == ['mappls', 'google', 'open-meteo', 'local']


@pytest.mark.asyncio
async def test_empty_query_async():
    places, meta = await search_places_with_meta('a', 'en', _settings())
    assert places == []
    assert meta.provider == 'none'


@pytest.mark.asyncio
async def test_whitespace_query_returns_nothing():
    assert await search_places('  ', 'en', _settings()) == []


@pytest.mark.asyncio
async def test_resolve_timezone_never_raises():
    place = await resolve_timezone(28.6, 77.2, 'Current location', _settings())
    assert place.timezone
    assert place.latitude == 28.6


@pytest.mark.asyncio
async def test_google_normalizes_autocomplete_and_details():
    def handler(request: httpx.Request) -> httpx.Response:
        if 'autocomplete' in str(request.url):
            return httpx.Response(200, json={
                'status': 'OK',
                'predictions': [{'place_id': 'pid-1', 'description': 'Chhaprauli, Baghpat, Uttar Pradesh, India'}],
            })
        if 'details' in str(request.url):
            return httpx.Response(200, json={
                'status': 'OK',
                'result': {
                    'name': 'Chhaprauli',
                    'formatted_address': 'Chhaprauli, Baghpat, Uttar Pradesh, India',
                    'geometry': {'location': {'lat': 29.3, 'lng': 77.2}},
                },
            })
        return httpx.Response(404)

    provider = GooglePlacesProvider('test-key')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        places = await provider.search(client, 'Chhap', 'en')
    assert len(places) == 1
    assert places[0].name.startswith('Chhaprauli')
    assert places[0].latitude == 29.3
    assert places[0].provider == 'google'
    assert places[0].provider_place_id == 'pid-1'


@pytest.mark.asyncio
async def test_google_invalid_response_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'status': 'UNKNOWN_ERROR'})

    provider = GooglePlacesProvider('test-key')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await provider.search(client, 'Delhi', 'en')


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [401, 403, 429, 500])
async def test_google_http_errors_trip_and_raise(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={'error': 'no'})

    provider = GooglePlacesProvider('test-key')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError):
            await provider.search(client, 'Delhi', 'en')


@pytest.mark.asyncio
async def test_google_timeout_falls_through_to_open_meteo(monkeypatch):
    async def boom(self, client, query, language):
        raise httpx.TimeoutException('slow')

    async def open_meteo(self, client, query, language):
        return [__import__('app.models', fromlist=['Location']).Location(
            name='Delhi, India', latitude=28.6, longitude=77.2, timezone='Asia/Kolkata', provider='open-meteo',
        )]

    monkeypatch.setattr(GooglePlacesProvider, 'search', boom)
    monkeypatch.setattr(OpenMeteoGeocodingProvider, 'search', open_meteo)
    places, meta = await search_places_with_meta('Delhi', 'en', _settings(google_places_api_key='k', google_places_enabled=True))
    assert places and places[0].provider == 'open-meteo'
    assert meta.provider == 'open-meteo'
    assert meta.fallback_used is True


@pytest.mark.asyncio
async def test_no_api_key_uses_open_meteo_or_local(monkeypatch):
    async def open_meteo(self, client, query, language):
        return []

    monkeypatch.setattr(OpenMeteoGeocodingProvider, 'search', open_meteo)
    places, meta = await search_places_with_meta('Mum', 'en', _settings())
    assert places[0].name == 'Mumbai'
    assert meta.provider == 'local'


@pytest.mark.asyncio
async def test_duplicate_results_are_removed(monkeypatch):
    async def open_meteo(self, client, query, language):
        from app.models import Location
        twin = Location(name='Delhi', latitude=28.6139, longitude=77.2090, timezone='Asia/Kolkata', provider='open-meteo')
        return [twin, twin]

    monkeypatch.setattr(OpenMeteoGeocodingProvider, 'search', open_meteo)
    places = await search_places('Delhi', 'en', _settings())
    assert len(places) == 1


@pytest.mark.asyncio
async def test_coordinate_validity_rejects_bad_google_geometry():
    def handler(request: httpx.Request) -> httpx.Response:
        if 'autocomplete' in str(request.url):
            return httpx.Response(200, json={'status': 'OK', 'predictions': [{'place_id': 'x', 'description': 'Bad'}]})
        return httpx.Response(200, json={'status': 'OK', 'result': {'geometry': {'location': {'lat': 999, 'lng': 0}}, 'name': 'Bad'}})

    provider = GooglePlacesProvider('test-key')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        places = await provider.search(client, 'Bad', 'en')
    assert places == []


@pytest.mark.asyncio
async def test_search_cache_coalesces_duplicate_queries(monkeypatch):
    calls = {'n': 0}

    async def open_meteo(self, client, query, language):
        calls['n'] += 1
        await asyncio.sleep(0.05)
        from app.models import Location
        return [Location(name='Goa', latitude=15.3, longitude=74.1, timezone='Asia/Kolkata', provider='open-meteo')]

    monkeypatch.setattr(OpenMeteoGeocodingProvider, 'search', open_meteo)
    await asyncio.gather(
        search_places_with_meta('Goa', 'en', _settings()),
        search_places_with_meta('Goa', 'en', _settings()),
    )
    assert calls['n'] == 1
    places, meta = await search_places_with_meta('Goa', 'en', _settings())
    assert places[0].name == 'Goa'
    assert meta.cached is True
    assert calls['n'] == 1


@pytest.mark.asyncio
async def test_google_reverse_geocode_builds_friendly_label():
    def handler(request: httpx.Request) -> httpx.Response:
        assert 'geocode' in str(request.url)
        return httpx.Response(200, json={
            'status': 'OK',
            'results': [{
                'address_components': [
                    {'long_name': 'New Delhi', 'types': ['locality']},
                    {'long_name': 'Delhi', 'types': ['administrative_area_level_1']},
                    {'long_name': 'India', 'types': ['country']},
                ],
                'formatted_address': 'New Delhi, Delhi, India',
            }],
        })

    provider = GooglePlacesProvider('test-key')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        label = await provider.reverse_geocode(client, 28.6126, 77.2093)
    assert label == 'New Delhi, Delhi, India'


@pytest.mark.asyncio
async def test_resolve_uses_reverse_geocode_for_generic_gps_name(monkeypatch):
    async def fake_reverse(self, client, latitude, longitude):
        return 'New Delhi, Delhi'

    monkeypatch.setattr(GooglePlacesProvider, 'reverse_geocode', fake_reverse)

    def forecast_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'timezone': 'Asia/Kolkata'})

    original = httpx.AsyncClient

    def wrapped(**kwargs):
        kwargs['transport'] = httpx.MockTransport(forecast_handler)
        return original(**kwargs)

    monkeypatch.setattr(httpx, 'AsyncClient', wrapped)
    place = await resolve_timezone(28.61, 77.20, 'Current location', _settings(google_places_api_key='k', google_places_enabled=True))
    assert place.name == 'New Delhi, Delhi'
    assert place.provider == 'google'


@pytest.mark.asyncio
async def test_local_provider_provenance():
    places = await LocalCityFallbackProvider().search(httpx.AsyncClient(), 'Del', 'en')
    assert places[0].provider == 'local'


@pytest.mark.asyncio
async def test_google_unavailable_open_meteo_fallback(monkeypatch):
    async def deny(self, client, query, language):
        raise RuntimeError('google_403')

    async def open_meteo(self, client, query, language):
        from app.models import Location
        return [Location(name='Pitampura, Delhi, India', latitude=28.7, longitude=77.1, timezone='Asia/Kolkata', provider='open-meteo')]

    monkeypatch.setattr(GooglePlacesProvider, 'search', deny)
    monkeypatch.setattr(OpenMeteoGeocodingProvider, 'search', open_meteo)
    places, meta = await search_places_with_meta('Pitampura', 'en', _settings(google_places_api_key='k', google_places_enabled=True))
    assert meta.provider == 'open-meteo'
    assert places[0].name.startswith('Pitampura')


@pytest.mark.asyncio
async def test_request_denied_long_cooldown_skips_google_on_next_search(monkeypatch):
    calls = {'n': 0}

    async def deny_once(self, client, query, language):
        calls['n'] += 1
        self._trip(24 * 60 * 60, billing=True)
        raise RuntimeError('google_403')

    async def open_meteo(self, client, query, language):
        from app.models import Location
        return [Location(name='Mumbai, Maharashtra, India', latitude=19.07, longitude=72.87, timezone='Asia/Kolkata', provider='open-meteo')]

    monkeypatch.setattr(GooglePlacesProvider, 'search', deny_once)
    monkeypatch.setattr(OpenMeteoGeocodingProvider, 'search', open_meteo)
    settings = _settings(google_places_api_key='k', google_places_enabled=True)
    first, _ = await search_places_with_meta('Mumbai', 'en', settings)
    assert first and first[0].provider == 'open-meteo'
    assert calls['n'] == 1
    # Second search must not call Google while billing cooldown is active.
    providers = build_search_providers(settings)
    assert 'google' not in [p.name for p in providers]
    second, meta = await search_places_with_meta('Mumbai City', 'en', settings)
    assert second and meta.provider == 'open-meteo'
    assert calls['n'] == 1


@pytest.mark.asyncio
async def test_free_reverse_geocode_without_google(monkeypatch):
    async def nominatim(client, latitude, longitude):
        return 'New Delhi, Delhi, India'

    monkeypatch.setattr('app.locations._nominatim_reverse', nominatim)

    def forecast_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'timezone': 'Asia/Kolkata'})

    original = httpx.AsyncClient

    def wrapped(**kwargs):
        kwargs['transport'] = httpx.MockTransport(forecast_handler)
        return original(**kwargs)

    monkeypatch.setattr(httpx, 'AsyncClient', wrapped)
    place = await resolve_timezone(28.61, 77.20, 'Current location', _settings())
    assert place.name == 'New Delhi, Delhi, India'
    assert place.provider == 'nominatim'


@pytest.mark.asyncio
async def test_zero_cost_searches_use_open_meteo(monkeypatch):
    async def open_meteo(self, client, query, language):
        from app.models import Location
        return [Location(name=f'{query}, India', latitude=20.0, longitude=77.0, timezone='Asia/Kolkata', provider='open-meteo')]

    monkeypatch.setattr(OpenMeteoGeocodingProvider, 'search', open_meteo)
    for q in ('Delhi', 'Pitampura', 'Chhaprauli', 'Mumbai', 'Bengaluru', 'Goa'):
        places, meta = await search_places_with_meta(q, 'en', _settings())
        assert meta.provider == 'open-meteo'
        assert places and q in places[0].name
