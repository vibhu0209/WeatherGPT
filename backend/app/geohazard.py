"""Infrastructure / landslide-adjacent hazard estimates from verified inputs.

This is NOT a geological ML model and NOT an official IMD/NDMA warning.
It combines:
- forecast rainfall totals (WeatherGPT fused hourly)
- Open-Meteo soil moisture
- Open-Meteo DEM elevation samples → rough slope proxy
- OpenStreetMap Overpass nearby roads / villages (when reachable)

Every output is classified WEATHERGPT_RISK_ESTIMATE.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import httpx

from .models import Location
from .security import display_place_name


_DISCLAIMER = (
    'WeatherGPT Risk Estimate — not an official geological survey or government warning. '
    'Follow IMD / NDMA / local disaster authorities for evacuation and road closures.'
)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def rainfall_totals_mm(hourly: list[dict], hours: int = 24) -> float | None:
    rows = hourly[:hours]
    values = [row.get('rain_mm') for row in rows if row.get('rain_mm') is not None]
    if not values:
        return None
    return round(sum(float(v) for v in values), 1)


async def fetch_soil_moisture(client: httpx.AsyncClient, location: Location) -> dict[str, Any]:
    response = await client.get(
        'https://api.open-meteo.com/v1/forecast',
        params={
            'latitude': location.latitude,
            'longitude': location.longitude,
            'hourly': 'soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm',
            'forecast_days': 1,
            'timezone': 'UTC',
        },
        timeout=20.0,
    )
    response.raise_for_status()
    data = response.json()
    hourly = data.get('hourly') or {}
    shallow_series = hourly.get('soil_moisture_0_to_1cm') or []
    mid_series = hourly.get('soil_moisture_3_to_9cm') or hourly.get('soil_moisture_1_to_3cm') or []
    current_shallow = next((v for v in shallow_series if v is not None), None)
    current_deeper = next((v for v in mid_series if v is not None), None)
    return {
        'soil_moisture_0_to_7cm': current_shallow,  # near-surface proxy key for scoring
        'soil_moisture_7_to_28cm': current_deeper,
        'unit': 'm3/m3',
        'source': 'open-meteo',
    }


async def fetch_slope_proxy(client: httpx.AsyncClient, location: Location) -> dict[str, Any]:
    """Rough slope % from DEM samples ~500 m N/E/S/W of the point."""
    # ~0.0045° latitude ≈ 500 m
    delta = 0.0045
    lats = [
        location.latitude,
        location.latitude + delta,
        location.latitude - delta,
        location.latitude,
        location.latitude,
    ]
    lons = [
        location.longitude,
        location.longitude,
        location.longitude,
        location.longitude + delta,
        location.longitude - delta,
    ]
    response = await client.get(
        'https://api.open-meteo.com/v1/elevation',
        params={
            'latitude': ','.join(f'{v:.5f}' for v in lats),
            'longitude': ','.join(f'{v:.5f}' for v in lons),
        },
        timeout=15.0,
    )
    response.raise_for_status()
    elevations = response.json().get('elevation') or []
    if len(elevations) < 5 or any(v is None for v in elevations[:5]):
        return {'elevation_m': None, 'slope_percent': None, 'source': 'open-meteo-elevation', 'status': 'unavailable'}
    centre = float(elevations[0])
    rises = [abs(float(elevations[i]) - centre) for i in range(1, 5)]
    run_m = _haversine_m(location.latitude, location.longitude, location.latitude + delta, location.longitude)
    if run_m <= 1:
        run_m = 500.0
    slope_percent = round((max(rises) / run_m) * 100.0, 1)
    return {
        'elevation_m': centre,
        'slope_percent': slope_percent,
        'sample_spacing_m': round(run_m),
        'source': 'open-meteo-elevation',
        'status': 'available',
        'note': 'Slope is a coarse DEM proxy (~90 m), not a surveyed terrain angle.',
    }


async def fetch_nearby_infrastructure(client: httpx.AsyncClient, location: Location, radius_m: int = 4000) -> dict[str, Any]:
    """OSM Overpass: highways + named places near the point."""
    query = f"""
    [out:json][timeout:18];
    (
      way(around:{radius_m},{location.latitude},{location.longitude})["highway"~"motorway|trunk|primary|secondary|tertiary"];
      node(around:{radius_m},{location.latitude},{location.longitude})["place"~"village|town|hamlet|suburb"];
    );
    out tags center 40;
    """
    try:
        response = await client.post(
            'https://overpass-api.de/api/interpreter',
            content=query.encode('utf-8'),
            headers={'Content-Type': 'text/plain'},
            timeout=20.0,
        )
        response.raise_for_status()
        elements = response.json().get('elements') or []
    except (httpx.HTTPError, ValueError, KeyError):
        return {
            'status': 'unavailable',
            'roads': [],
            'settlements': [],
            'source': 'openstreetmap-overpass',
            'message': 'OpenStreetMap infrastructure lookup is temporarily unavailable.',
        }

    roads: list[dict[str, Any]] = []
    settlements: list[dict[str, Any]] = []
    for element in elements:
        tags = element.get('tags') or {}
        centre = element.get('center') or {}
        lat = centre.get('lat', element.get('lat'))
        lon = centre.get('lon', element.get('lon'))
        if tags.get('highway'):
            name = tags.get('name') or tags.get('ref') or tags['highway']
            roads.append({
                'name': name,
                'class': tags.get('highway'),
                'latitude': lat,
                'longitude': lon,
            })
        if tags.get('place'):
            settlements.append({
                'name': tags.get('name') or tags.get('place'),
                'place': tags.get('place'),
                'latitude': lat,
                'longitude': lon,
            })

    # Prefer named / higher-class roads for the dashboard.
    class_rank = {'motorway': 0, 'trunk': 1, 'primary': 2, 'secondary': 3, 'tertiary': 4}
    roads.sort(key=lambda item: (class_rank.get(item['class'], 9), item['name']))
    return {
        'status': 'available',
        'radius_m': radius_m,
        'roads': roads[:12],
        'settlements': settlements[:12],
        'source': 'openstreetmap-overpass',
    }


def score_hazard(
    rain_24h_mm: float | None,
    rain_48h_mm: float | None,
    soil_shallow: float | None,
    slope_percent: float | None,
    official_mentions_landslide: bool,
) -> dict[str, Any]:
    """Transparent additive score. Higher = more concern. Never claims certainty."""
    points = 0
    factors: list[str] = []

    if official_mentions_landslide:
        points += 50
        factors.append('Official warning text mentions landslide / slope / debris risk')

    if rain_24h_mm is not None:
        if rain_24h_mm >= 100:
            points += 35
            factors.append(f'Very heavy 24h rain total ({rain_24h_mm} mm)')
        elif rain_24h_mm >= 50:
            points += 25
            factors.append(f'Heavy 24h rain total ({rain_24h_mm} mm)')
        elif rain_24h_mm >= 25:
            points += 15
            factors.append(f'Moderate-to-heavy 24h rain total ({rain_24h_mm} mm)')
        elif rain_24h_mm >= 10:
            points += 8
            factors.append(f'Elevated 24h rain total ({rain_24h_mm} mm)')

    if rain_48h_mm is not None and rain_24h_mm is not None and rain_48h_mm - rain_24h_mm >= 40:
        points += 10
        factors.append(f'Additional rain in 24–48h window ({round(rain_48h_mm - rain_24h_mm, 1)} mm)')

    if soil_shallow is not None:
        # Volumetric water content — saturated soils typically approach ~0.4+ depending on soil type.
        if soil_shallow >= 0.40:
            points += 20
            factors.append(f'High near-surface soil moisture ({soil_shallow} m³/m³)')
        elif soil_shallow >= 0.30:
            points += 12
            factors.append(f'Elevated near-surface soil moisture ({soil_shallow} m³/m³)')

    if slope_percent is not None:
        if slope_percent >= 25:
            points += 20
            factors.append(f'Steep local DEM slope proxy ({slope_percent}%)')
        elif slope_percent >= 12:
            points += 12
            factors.append(f'Moderate local DEM slope proxy ({slope_percent}%)')
        elif slope_percent >= 6:
            points += 6
            factors.append(f'Mild local DEM slope proxy ({slope_percent}%)')

    if points >= 55:
        level, label = 'red', 'High concern'
        lead = (
            'High concern — weather, terrain and/or official cues suggest elevated landslide / '
            'road-cut risk. Treat nearby steep roads and settlements as potentially disrupted.'
        )
    elif points >= 30:
        level, label = 'orange', 'Elevated concern'
        lead = (
            'Elevated concern — rainfall and terrain factors raise landslide / road-block potential. '
            'Avoid unnecessary travel on steep or cut-hill roads if rain continues.'
        )
    elif points >= 15:
        level, label = 'yellow', 'Watch'
        lead = (
            'Watch — some rainfall / moisture / slope factors are present. '
            'Stay alert to official warnings and local road advisories.'
        )
    else:
        level, label = 'green', 'Lower concern from available inputs'
        lead = (
            'Lower concern from available rainfall, soil moisture and slope inputs — '
            'this is not a guarantee of safety. Still check official warnings.'
        )

    return {
        'score': points,
        'severity': level,
        'label': label,
        'decision': lead,
        'factors': factors,
    }


def _official_mentions_geohazard(alerts: list[dict]) -> bool:
    words = (
        'landslide', 'landslip', 'mudslide', 'debris', 'slope', 'भूस्खलन',
        'flash flood', 'cloudburst', 'अतिवृष्टि',
    )
    for alert in alerts or []:
        blob = ' '.join(
            str(alert.get(key) or '')
            for key in ('headline', 'event', 'description', 'instruction')
        ).lower()
        if any(word in blob for word in words):
            return True
    return False


async def assess_infrastructure_hazard(
    location: Location,
    hourly: list[dict],
    official_alerts: list[dict] | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    owns_client = client is None
    client = client or httpx.AsyncClient()
    sources: list[str] = ['weathergpt-forecast']
    try:
        rain_24 = rainfall_totals_mm(hourly, 24)
        rain_48 = rainfall_totals_mm(hourly, 48)
        soil: dict[str, Any] = {'status': 'unavailable'}
        slope: dict[str, Any] = {'status': 'unavailable'}
        infra: dict[str, Any] = {'status': 'unavailable', 'roads': [], 'settlements': []}
        try:
            soil = await fetch_soil_moisture(client, location)
            sources.append('open-meteo-soil')
        except (httpx.HTTPError, ValueError, KeyError):
            soil = {'soil_moisture_0_to_7cm': None, 'soil_moisture_7_to_28cm': None, 'status': 'unavailable', 'source': 'open-meteo'}
        try:
            slope = await fetch_slope_proxy(client, location)
            if slope.get('status') == 'available':
                sources.append('open-meteo-elevation')
        except (httpx.HTTPError, ValueError, KeyError):
            slope = {'elevation_m': None, 'slope_percent': None, 'status': 'unavailable', 'source': 'open-meteo-elevation'}
        try:
            infra = await fetch_nearby_infrastructure(client, location)
            if infra.get('status') == 'available':
                sources.append('openstreetmap-overpass')
        except (httpx.HTTPError, ValueError, KeyError):
            infra = {
                'status': 'unavailable', 'roads': [], 'settlements': [],
                'source': 'openstreetmap-overpass',
                'message': 'OpenStreetMap infrastructure lookup is temporarily unavailable.',
            }

        official = official_alerts or []
        scored = score_hazard(
            rain_24,
            rain_48,
            soil.get('soil_moisture_0_to_7cm'),
            slope.get('slope_percent'),
            _official_mentions_geohazard(official),
        )

        # Prioritize response: roads that could cut connectivity first.
        priority_roads = infra.get('roads') or []
        priority_places = infra.get('settlements') or []

        return {
            'classification': 'WEATHERGPT_RISK_ESTIMATE',
            'kind': 'landslide_infrastructure',
            'place': display_place_name(location.name),
            'decision': scored['decision'],
            'severity': scored['severity'],
            'label': scored['label'],
            'score': scored['score'],
            'factors': scored['factors'],
            'inputs': {
                'rain_24h_mm': rain_24,
                'rain_48h_mm': rain_48,
                'soil_moisture_0_to_7cm': soil.get('soil_moisture_0_to_7cm'),
                'soil_moisture_7_to_28cm': soil.get('soil_moisture_7_to_28cm'),
                'elevation_m': slope.get('elevation_m'),
                'slope_percent': slope.get('slope_percent'),
                'slope_note': slope.get('note'),
            },
            'infrastructure': {
                'status': infra.get('status'),
                'radius_m': infra.get('radius_m'),
                'roads_at_risk_priority': priority_roads,
                'settlements_nearby': priority_places,
                'message': infra.get('message'),
            },
            'map_points': [
                *[{
                    'type': 'road',
                    'name': road['name'],
                    'class': road.get('class'),
                    'latitude': road.get('latitude'),
                    'longitude': road.get('longitude'),
                    'priority': scored['severity'],
                } for road in priority_roads if road.get('latitude') is not None],
                *[{
                    'type': 'settlement',
                    'name': place['name'],
                    'place': place.get('place'),
                    'latitude': place.get('latitude'),
                    'longitude': place.get('longitude'),
                    'priority': scored['severity'],
                } for place in priority_places if place.get('latitude') is not None],
            ],
            'disclaimer': _DISCLAIMER,
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'sources': list(dict.fromkeys(sources)),
        }
    finally:
        if owns_client:
            await client.aclose()
