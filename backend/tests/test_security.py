import asyncio
import logging

from fastapi.testclient import TestClient

from app.ai import GeminiPolisher
from app.cache import MemoryCacheBackend
from app.main import app
from app.models import Forecast, Location, Point
from app.security import (
    assert_https_allowlisted,
    geohash_encode,
    public_location,
    redact_coordinates,
    redact_secrets,
    sanitize_gemini_question,
    weather_cache_key,
)
from app.weather import WeatherService
from datetime import datetime, timedelta, timezone


client = TestClient(app)


def test_geohash_groups_nearby_coordinates():
    a = weather_cache_key(28.6139, 77.2090, 'Asia/Kolkata')
    b = weather_cache_key(28.6145, 77.2095, 'Asia/Kolkata')
    c = weather_cache_key(19.0760, 72.8777, 'Asia/Kolkata')
    assert a == b
    assert a != c
    assert len(geohash_encode(28.6, 77.2, 5)) == 5


def test_coordinate_redaction_and_public_location():
    text = 'Meet me at lat=28.6139, lon=77.2090 tomorrow'
    assert '28.6139' not in redact_coordinates(text)
    assert '[location]' in redact_coordinates(text)
    assert '[REDACTED]' in redact_secrets('https://example/?appid=SECRET')
    place = public_location(Location(name='Delhi', latitude=28.6, longitude=77.2))
    assert place['name'] == 'Delhi'
    assert place['latitude'] is None and place['longitude'] is None


def test_https_allowlist_blocks_private_and_http():
    assert assert_https_allowlisted('https://alerts.example.gov/cap.xml', {'alerts.example.gov'}) == 'alerts.example.gov'
    try:
        assert_https_allowlisted('http://alerts.example.gov/cap.xml', {'alerts.example.gov'})
        assert False, 'http should fail'
    except ValueError:
        pass
    try:
        assert_https_allowlisted('https://169.254.169.254/latest', {'169.254.169.254'})
        assert False, 'link-local should fail'
    except ValueError:
        pass


def test_gemini_question_sanitization():
    cleaned = sanitize_gemini_question('Will it rain at 28.613900, 77.209000?')
    assert '28.613900' not in cleaned
    assert '[location]' in cleaned


def test_gemini_budget_returns_draft_when_exhausted():
    polisher = GeminiPolisher(max_calls_per_minute=0)
    polisher.settings.gemini_api_key = 'x'
    polisher.settings.gemini_model = 'models/test'

    async def run():
        return await polisher.polish('Q', 'Draft answer', 'en')

    assert asyncio.run(run()) == 'Draft answer'


def test_rate_limiting_returns_safe_error():
    limited = __import__('app.main', fromlist=['rate_limiter']).rate_limiter
    for _ in range(90):
        assert limited.allow('abuse-ip')
    assert limited.allow('abuse-ip') is False
    assert limited.allow('other-ip') is True


def test_ready_endpoint_and_security_headers():
    response = client.get('/ready')
    assert response.status_code == 200
    assert response.json()['status'] == 'ready'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'


def test_post_bundle_avoids_coordinates_in_path(monkeypatch):
    from app import main

    async def weather(_):
        return {'hourly': [], 'daily': [], 'is_stale': False, 'retrieved_at': '2026-01-01T00:00:00+00:00',
            'sources': [], 'source_count': 0, 'agreement': 'unavailable', 'provider_status': []}

    async def official(_):
        return {'status': 'unavailable', 'alerts': [], 'message': 'Official warnings unavailable.'}

    monkeypatch.setattr(main.service, 'bundle', weather)
    monkeypatch.setattr(main.alert_service, 'official', official)
    response = client.post('/v1/weather/bundle', json={
        'latitude': 28.6, 'longitude': 77.2, 'name': 'Delhi', 'timezone': 'Asia/Kolkata', 'hours': 24,
    })
    assert response.status_code == 200
    assert '28.6' not in str(response.request.url)


def test_chat_context_omits_precise_coordinates(monkeypatch, caplog):
    from app import main

    async def weather(_):
        return {'hourly': [], 'is_stale': False, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'sources': ['open-meteo'], 'agreement': 'single_source'}

    async def official(_):
        return {'status': 'unavailable', 'alerts': [], 'message': 'unknown'}

    monkeypatch.setattr(main.service, 'bundle', weather)
    monkeypatch.setattr(main.alert_service, 'official', official)
    with caplog.at_level(logging.INFO, logger='weathergpt.request'):
        response = client.post('/v1/chat/message', json={
            'text': 'Any warnings?',
            'location': {'name': 'Delhi', 'latitude': 28.6139, 'longitude': 77.209, 'timezone': 'Asia/Kolkata'},
        })
    assert response.status_code == 200
    context = response.json()['conversation_context']['resolved_location']
    assert context['latitude'] is None and context['longitude'] is None
    assert '28.6139' not in caplog.text
    assert '77.209' not in caplog.text


def test_weather_cache_coalesces_same_grid():
    service = WeatherService(cache=MemoryCacheBackend())
    calls = {'count': 0}

    class FakeProvider:
        id = 'fake'
        enabled = True
        model_family = 'fake'

        def __init__(self, client, settings):
            pass

        async def forecast(self, loc):
            calls['count'] += 1
            now = datetime.now(timezone.utc)
            return Forecast(provider='fake', model_family='fake', retrieved_at=now, hourly=[
                Point(time=now + timedelta(hours=1), temperature=30.0, rain_chance=10.0, wind_ms=2.0)
            ])

        def health(self):
            return {'provider': 'fake', 'status': 'available'}

    async def run():
        import app.weather as weather_module
        original = weather_module.PROVIDERS
        weather_module.PROVIDERS = [FakeProvider]
        try:
            first = asyncio.create_task(service.bundle(Location(name='A', latitude=28.6139, longitude=77.2090)))
            second = asyncio.create_task(service.bundle(Location(name='B', latitude=28.6141, longitude=77.2092)))
            results = await asyncio.gather(first, second)
            assert results[0]['location']['name'] == 'A'
            assert results[1]['location']['name'] == 'B'
            assert calls['count'] == 1
        finally:
            weather_module.PROVIDERS = original

    asyncio.run(run())
