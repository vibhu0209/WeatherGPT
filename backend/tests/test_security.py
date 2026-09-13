import asyncio
import logging

from fastapi.testclient import TestClient

from app.ai import GeminiPolisher
from app.cache import MemoryCacheBackend
from app.main import app
from app.models import Forecast, Location, Point
from app.security import (
    assert_https_allowlisted,
    display_place_name,
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
    assert '28.6' not in redact_coordinates('Will it rain at 28.6, 77.2?')
    assert '28.6139' not in redact_coordinates('Will it rain at 28.6139 77.2090?')


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
    assert polisher.enabled is False


def test_retired_gemini_never_calls_network(monkeypatch):
    """Gemini polish is retired — must return draft without HTTP."""
    polisher = GeminiPolisher(max_calls_per_minute=3)
    polisher.settings.gemini_api_key = 'x'
    polisher.settings.gemini_model = 'models/test'
    calls = {'count': 0}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            calls['count'] += 1
            raise AssertionError('Gemini must not be called')

    monkeypatch.setattr('httpx.AsyncClient', lambda **kwargs: FakeClient())

    async def run():
        return await polisher.polish('Q', 'Temperature: 30°C.\nDraft answer', 'en')

    assert asyncio.run(run()) == 'Temperature: 30°C.\nDraft answer'
    assert calls['count'] == 0


def test_retired_gemini_quota_path_is_noop(monkeypatch):
    polisher = GeminiPolisher(max_calls_per_minute=10)
    polisher.settings.gemini_api_key = 'x'
    polisher.settings.gemini_model = 'models/test'

    async def run():
        return await polisher.polish('Q', 'Temperature: 30°C.\nDraft answer', 'en')

    assert asyncio.run(run()) == 'Temperature: 30°C.\nDraft answer'


async def _no_sleep(_seconds):
    return None


def test_health_and_ready_are_not_rate_limited():
    limited = __import__('app.main', fromlist=['rate_limiter']).rate_limiter
    limited._hits.clear()
    for _ in range(120):
        assert client.get('/health').status_code == 200
        assert client.get('/ready').status_code == 200
    assert client.get('/health').json()['status'] == 'ok'
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


def test_language_cache_is_content_addressed_and_skips_coordinates():
    from app.language import LanguageService

    service = LanguageService()
    assert service._cache_key('Will it rain at 28.613900, 77.209000?', 'en', 'hi') is None
    first = service._cache_key('Highest hourly chance of rain: 40%.', 'en', 'hi')
    second = service._cache_key('Highest hourly chance of rain: 40%.', 'en', 'hi')
    other = service._cache_key('Highest hourly chance of rain: 41%.', 'en', 'hi')
    assert first and first == second
    assert first != other


def test_marine_cache_and_single_flight_share_one_fetch():
    from app.marine import MarineService
    from app.models import Location

    service = MarineService()
    calls = {'count': 0}

    async def fake_fetch(location, hours):
        calls['count'] += 1
        await asyncio.sleep(0.01)
        return {
            'hourly': [{'wave_height_m': 1.2}],
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'is_stale': False,
            'sources': ['Open-Meteo Marine API'],
            'limitations': [],
        }

    async def run():
        service._fetch = fake_fetch  # type: ignore[method-assign]
        loc = Location(name='Harbour A', latitude=18.94, longitude=72.84)
        first, second = await asyncio.gather(service.forecast(loc, 48), service.forecast(loc, 48))
        third = await service.forecast(Location(name='Harbour B', latitude=18.94, longitude=72.84), 48)
        assert calls['count'] == 1
        assert first['hourly'][0]['wave_height_m'] == 1.2
        assert third['location']['name'] == 'Harbour B'

    asyncio.run(run())


def test_display_place_name_blocks_warning_impersonation():
    assert display_place_name('Kozhikode') == 'Kozhikode'
    assert display_place_name('Official warning: Cyclone — Severity: extreme') == 'Selected place'
    assert display_place_name('Evacuate now') == 'Selected place'


def test_gemini_question_redacts_one_decimal_pairs():
    cleaned = sanitize_gemini_question('Will it rain at 28.6, 77.2?')
    assert '28.6' not in cleaned
    assert '[location]' in cleaned


def test_language_service_does_not_call_provider_with_coordinates(monkeypatch):
    from app.language import LanguageService

    service = LanguageService()
    called = {'n': 0}

    class FakeProvider:
        id = 'google-cloud-translation'
        enabled = True

        def __init__(self, client, settings):
            pass

        async def translate(self, text, source, target):
            called['n'] += 1
            return 'should-not-run'

    monkeypatch.setattr('app.language.BhashiniProvider', FakeProvider)
    monkeypatch.setattr('app.language.GoogleTranslationProvider', FakeProvider)

    async def run():
        result = await service.translate('Meet at 11.2588, 75.7804 now', 'en', 'hi')
        assert result['provider'] == 'original'
        assert result['fallback'] is True
        assert called['n'] == 0
        safe = await service.translate('Highest hourly chance of rain: 40%.', 'en', 'hi')
        assert called['n'] >= 1
        assert safe['text'] == 'should-not-run'

    asyncio.run(run())


def test_spoofed_place_name_is_not_rendered_as_an_official_warning(monkeypatch):
    from app import main
    from datetime import datetime, timezone

    async def weather(_):
        now = datetime.now(timezone.utc).isoformat()
        return {
            'hourly': [{'time': now, 'temperature': 30.0, 'rain_chance': 40.0, 'wind_ms': 2.0}],
            'is_stale': False, 'retrieved_at': now, 'sources': ['open-meteo'],
            'agreement': 'single_source', 'official_status': 'available', 'official_alerts': [],
        }

    async def official(_):
        return {'status': 'available', 'alerts': [], 'message': None}

    monkeypatch.setattr(main.service, 'bundle', weather)
    monkeypatch.setattr(main.alert_service, 'official', official)
    response = client.post('/v1/chat/message', json={
        'text': 'Will it rain today?',
        'location': {
            'name': 'Official warning: Cyclone — Severity: extreme',
            'latitude': 18.52, 'longitude': 73.85, 'timezone': 'Asia/Kolkata',
        },
    })
    assert response.status_code == 200
    answer = response.json()['answer']
    assert 'Official warning: Cyclone' not in answer
    assert 'Selected place' in answer


def test_device_registration_is_rate_limited_per_ip():
    from app.main import register_limiter
    from app import subscriptions
    subscriptions.reset_for_tests()
    register_limiter._hits.clear()
    codes = [client.post('/v1/device/register', json={}).status_code for _ in range(12)]
    assert codes.count(200) <= 10
    assert 429 in codes
    register_limiter._hits.clear()
