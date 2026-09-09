import pytest

from app.locations import _popular_matches, resolve_timezone, search_places
from app.models import Settings


@pytest.mark.asyncio
async def test_search_falls_back_to_popular_india_cities():
    places = await search_places('Del', 'en', Settings(google_places_api_key='', google_maps_api_key='', mappls_access_token=''))
    assert places
    assert any('Delhi' in place.name for place in places)


def test_popular_matches_are_india_first():
    assert [p.name for p in _popular_matches('mum')] == ['Mumbai']


@pytest.mark.asyncio
async def test_resolve_timezone_never_raises():
    place = await resolve_timezone(28.6, 77.2, 'Current location')
    assert place.timezone
    assert place.latitude == 28.6
