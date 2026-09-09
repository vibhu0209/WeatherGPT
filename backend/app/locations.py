from __future__ import annotations

import httpx

from .models import Location, Settings

POPULAR_INDIA = [
    Location(name='Delhi', latitude=28.6139, longitude=77.2090, timezone='Asia/Kolkata'),
    Location(name='Mumbai', latitude=19.0760, longitude=72.8777, timezone='Asia/Kolkata'),
    Location(name='Bengaluru', latitude=12.9716, longitude=77.5946, timezone='Asia/Kolkata'),
    Location(name='Chennai', latitude=13.0827, longitude=80.2707, timezone='Asia/Kolkata'),
    Location(name='Kolkata', latitude=22.5726, longitude=88.3639, timezone='Asia/Kolkata'),
    Location(name='Hyderabad', latitude=17.3850, longitude=78.4867, timezone='Asia/Kolkata'),
    Location(name='Pune', latitude=18.5204, longitude=73.8567, timezone='Asia/Kolkata'),
    Location(name='Ahmedabad', latitude=23.0225, longitude=72.5714, timezone='Asia/Kolkata'),
    Location(name='Jaipur', latitude=26.9124, longitude=75.7873, timezone='Asia/Kolkata'),
    Location(name='Lucknow', latitude=26.8467, longitude=80.9462, timezone='Asia/Kolkata'),
    Location(name='Patna', latitude=25.5941, longitude=85.1376, timezone='Asia/Kolkata'),
    Location(name='Bhopal', latitude=23.2599, longitude=77.4126, timezone='Asia/Kolkata'),
    Location(name='Bhubaneswar', latitude=20.2961, longitude=85.8245, timezone='Asia/Kolkata'),
    Location(name='Guwahati', latitude=26.1445, longitude=91.7362, timezone='Asia/Kolkata'),
    Location(name='Kochi', latitude=9.9312, longitude=76.2673, timezone='Asia/Kolkata'),
]


def _popular_matches(query: str) -> list[Location]:
    q = query.strip().lower()
    return [place for place in POPULAR_INDIA if q in place.name.lower()][:8]


async def _open_meteo(client: httpx.AsyncClient, query: str, language: str) -> list[Location]:
    response = await client.get(
        'https://geocoding-api.open-meteo.com/v1/search',
        params={'name': query, 'count': 8, 'language': language, 'countryCode': 'IN'},
    )
    response.raise_for_status()
    places = []
    for row in response.json().get('results') or []:
        places.append(Location(
            name=', '.join(filter(None, [row.get('name'), row.get('admin1'), row.get('country')])),
            latitude=float(row['latitude']),
            longitude=float(row['longitude']),
            timezone=row.get('timezone') or 'Asia/Kolkata',
        ))
    return places


async def _google_places(client: httpx.AsyncClient, query: str, api_key: str) -> list[Location]:
    auto = await client.get(
        'https://maps.googleapis.com/maps/api/place/autocomplete/json',
        params={'input': query, 'key': api_key, 'components': 'country:in', 'types': 'geocode'},
    )
    auto.raise_for_status()
    payload = auto.json()
    if payload.get('status') not in {'OK', 'ZERO_RESULTS'}:
        raise ValueError(payload.get('status', 'google_places_error'))
    places: list[Location] = []
    for prediction in (payload.get('predictions') or [])[:6]:
        place_id = prediction.get('place_id')
        if not place_id:
            continue
        details = await client.get(
            'https://maps.googleapis.com/maps/api/place/details/json',
            params={'place_id': place_id, 'fields': 'geometry,name,formatted_address', 'key': api_key},
        )
        details.raise_for_status()
        result = details.json().get('result') or {}
        location = ((result.get('geometry') or {}).get('location')) or {}
        if 'lat' not in location or 'lng' not in location:
            continue
        name = result.get('formatted_address') or result.get('name') or prediction.get('description') or 'Selected place'
        places.append(Location(name=name[:120], latitude=float(location['lat']), longitude=float(location['lng']), timezone='Asia/Kolkata'))
    return places


async def _mappls_places(client: httpx.AsyncClient, query: str, token: str) -> list[Location]:
    auto = await client.get(
        'https://search.mappls.com/search/places/autosuggest/json',
        params={'query': query, 'access_token': token},
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
                params={'access_token': token},
            )
            entity.raise_for_status()
            data = entity.json()
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            name = data.get('address') or data.get('name') or name
        if latitude is None or longitude is None:
            continue
        places.append(Location(name=str(name)[:120], latitude=float(latitude), longitude=float(longitude), timezone='Asia/Kolkata'))
    return places


async def search_places(query: str, language: str = 'en', settings: Settings | None = None) -> list[Location]:
    settings = settings or Settings()
    q = query.strip()
    if len(q) < 2:
        return []
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        providers = []
        google_key = settings.google_places_api_key or settings.google_maps_api_key
        if google_key:
            providers.append(('google', lambda: _google_places(client, q, google_key)))
        if settings.mappls_access_token:
            providers.append(('mappls', lambda: _mappls_places(client, q, settings.mappls_access_token)))
        providers.append(('open-meteo', lambda: _open_meteo(client, q, language)))
        for _, fetch in providers:
            try:
                places = await fetch()
                if places:
                    return places
            except Exception:
                continue
    return _popular_matches(q)


async def resolve_timezone(latitude: float, longitude: float, name: str) -> Location:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            response = await client.get(
                'https://api.open-meteo.com/v1/forecast',
                params={'latitude': latitude, 'longitude': longitude, 'timezone': 'auto', 'forecast_days': 1, 'hourly': 'temperature_2m'},
            )
            response.raise_for_status()
            timezone_name = response.json().get('timezone') or 'Asia/Kolkata'
            return Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone_name)
    except Exception:
        # India-first default so onboarding never hangs on reverse-geocode failures.
        return Location(name=name, latitude=latitude, longitude=longitude, timezone='Asia/Kolkata')
