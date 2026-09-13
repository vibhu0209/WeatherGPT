from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from app.chat_tools import select_tool
from app.main import app
from app.models import ChatRequest, Location
from app.tools import TOOL_REGISTRY

LOC = Location(name='Pune', latitude=18.52, longitude=73.85)
NOW = datetime(2026, 9, 11, 6, 0, tzinfo=timezone.utc)
MUMBAI = Location(name='Mumbai', latitude=19.07, longitude=72.87)


DELHI = Location(name='Delhi', latitude=28.6, longitude=77.2)
CHANDIGARH = Location(name='Chandigarh', latitude=30.73, longitude=76.78)


def _bundle():
    hours = []
    for index in range(72):
        hours.append({
            'time': (NOW + timedelta(hours=index)).isoformat(),
            'temperature': 18 + (index % 24) * 0.5,
            'rain_chance': 40,
            'wind_ms': 3.3,
            'humidity': 60,
        })
    return {
        'hourly': hours,
        'daily': [
            {'date': '2026-09-11', 'temperature_min': 18, 'temperature_max': 30.5, 'rain_chance_max': 40, 'wind_max_ms': 3.3},
            {'date': '2026-09-12', 'temperature_min': 20, 'temperature_max': 32.0, 'rain_chance_max': 55, 'wind_max_ms': 4.0},
        ],
        'is_stale': False,
        'retrieved_at': NOW.isoformat(),
        'sources': ['open-meteo'],
        'agreement': 'single_source',
        'scores': {
            'farming': {'score': 70, 'label': 'Moderate conditions', 'profile': 'farming',
                        'disclaimer': 'This score is not an official safety certification. Check official warnings before acting.'},
            'general': {'score': 82, 'label': 'Good conditions', 'profile': 'general',
                        'disclaimer': 'This score is not an official safety certification. Check official warnings before acting.'},
        },
    }


def _patch_chat_backends(monkeypatch, *, alerts=None):
    from datetime import datetime as real_datetime

    from app import chat_tools, main

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW

    monkeypatch.setattr('app.chat.datetime', FrozenDateTime)

    async def weather(_):
        return _bundle()

    async def official(_):
        return {'status': 'available', 'alerts': alerts or [], 'message': 'available'}

    async def climate(*_args, **_kwargs):
        return {
            'metric': 'temperature', 'trend_per_decade': 0.2, 'unit': '°C',
            'period': {'start_year': 2015, 'end_year': 2025}, 'coverage': 0.95,
            'generated_at': NOW.isoformat(), 'source': 'era5',
        }

    async def marine(*_args, **_kwargs):
        return {'hourly': [{'wave_height_m': 1.2, 'wave_period_s': 7}], 'retrieved_at': NOW.isoformat(), 'sources': ['open-meteo-marine']}

    monkeypatch.setattr(chat_tools.service, 'bundle', weather)
    monkeypatch.setattr(main.service, 'bundle', weather)
    monkeypatch.setattr('app.tools.service.bundle', weather)
    monkeypatch.setattr(chat_tools.alert_service, 'official', official)
    monkeypatch.setattr(main.alert_service, 'official', official)
    monkeypatch.setattr('app.tools.climate_service.summary', climate)
    monkeypatch.setattr('app.tools.marine_service.forecast', marine)

    async def no_orchestrator(_request):
        return None

    monkeypatch.setattr('app.groq_orchestrator.orchestrate_chat', no_orchestrator)
    monkeypatch.setattr('app.gemini_orchestrator.orchestrate_chat', no_orchestrator)
    return TestClient(app)


def test_parse_hour_window_reads_clock_range():
    from zoneinfo import ZoneInfo

    from app.chat import parse_hour_window
    local_now = NOW.astimezone(ZoneInfo('Asia/Kolkata'))
    start, end = parse_hour_window('Will it rain between 3 and 6?', 'Asia/Kolkata', local_now)
    assert start is not None and end is not None
    assert start.hour == 15 and end.hour == 18


def test_select_tool_maps_representative_questions():
    cases = {
        'What is the weather today?': 'get_current_weather',
        'Hourly forecast please': 'get_hourly_forecast',
        'Daily forecast this week': 'get_daily_forecast',
        'Any warnings?': 'get_active_alerts',
        'When should I work outside?': 'get_weather_score',
        'Has it been hotter over the years?': 'get_climate_summary',
        'marine conditions for fishing': 'get_marine_forecast',
        'Which providers are available?': 'get_provider_status',
        'Show my saved locations': 'get_saved_locations',
        'Notify me about rain': 'set_alert_rule',
        'IMD agromet advisory': 'get_agromet_advisory',
        'What is the weather now?': 'get_current_weather',
        'Will it rain between 3 and 6?': 'get_hourly_forecast',
        'What about tomorrow?': 'get_daily_forecast',
        'Any alerts near me?': 'get_active_alerts',
        "What's my weather score?": 'get_weather_score',
        'Should I sow seeds today?': 'get_weather_score',
        'Can I dry clothes outside?': 'get_weather_score',
        'Is it safe to drive this evening?': 'get_weather_score',
        'Compare Delhi and Chandigarh tomorrow.': 'compare_locations',
        'What are the sea conditions?': 'get_marine_forecast',
        'Has Delhi become hotter over the last decade?': 'get_climate_summary',
        'What are my saved locations?': 'get_saved_locations',
        'Set a rain alert.': 'set_alert_rule',
        'What is the farming advisory?': 'get_agromet_advisory',
    }
    for text, expected in cases.items():
        assert select_tool(ChatRequest(text=text, location=LOC)) == expected, text
    assert select_tool(ChatRequest(text='compare rain tomorrow', location=LOC, secondary_location=MUMBAI)) == 'compare_locations'
    assert select_tool(ChatRequest(text='Will it rain today?', location=LOC, secondary_location=MUMBAI)) == 'compare_locations'
    assert select_tool(ChatRequest(text='মাছ ধরার জন্য সমুদ্রের অবস্থা কেমন?', location=LOC)) == 'get_marine_forecast'
    assert select_tool(ChatRequest(text='আবহাওয়ার সতর্কতা আছে কি?', location=LOC)) == 'get_active_alerts'
    assert select_tool(ChatRequest(text='গত ১০ বছরে এই জায়গা কি গরম হয়েছে?', location=LOC)) == 'get_climate_summary'


def test_every_registry_tool_is_reachable_from_chat(monkeypatch):
    from app.chat_tools import INTERNAL_TOOLS, USER_FACING_TOOLS

    assert USER_FACING_TOOLS == set(TOOL_REGISTRY)
    assert INTERNAL_TOOLS == frozenset()
    client = _patch_chat_backends(monkeypatch)
    questions = {
        'get_current_weather': {'text': 'Will it rain today?'},
        'get_hourly_forecast': {'text': 'Hourly forecast please'},
        'get_daily_forecast': {'text': 'Daily forecast this week'},
        'get_active_alerts': {'text': 'Any warnings?'},
        'get_weather_score': {'text': 'When should I work outside?'},
        'get_climate_summary': {'text': 'Has monsoon rainfall changed over the years?'},
        'get_marine_forecast': {'text': 'marine conditions for fishing'},
        'get_provider_status': {'text': 'Which providers are available?'},
        'get_saved_locations': {'text': 'Show my saved locations', 'saved_locations': [LOC.model_dump(mode='json'), MUMBAI.model_dump(mode='json')]},
        'set_alert_rule': {'text': 'Notify me about rain'},
        'get_agromet_advisory': {'text': 'IMD agromet advisory'},
        'compare_locations': {'text': 'compare rain tomorrow', 'secondary_location': MUMBAI.model_dump(mode='json')},
    }
    assert set(questions) == set(TOOL_REGISTRY)
    for name, extra in questions.items():
        body = {'location': LOC.model_dump(mode='json'), **extra}
        response = client.post('/v1/chat/message', json=body)
        assert response.status_code == 200, (name, response.text)
        payload = response.json()
        assert payload['tool'] == name
        assert payload['answer']
        facts = {
            'get_current_weather': ('40', '°C'),
            'get_hourly_forecast': ('40', '°C'),
            'get_daily_forecast': ('30.5', '40'),
            'get_active_alerts': ('warning',),
            'get_weather_score': ('82', '/100'),
            'get_climate_summary': ('0.2', 'ERA5'),
            'get_marine_forecast': ('1.2', 'wave'),
            'get_provider_status': ('provider',),
            'get_saved_locations': ('Pune', 'Mumbai'),
            'set_alert_rule': ('rain',),
            'get_agromet_advisory': ('not connected',),
            'compare_locations': ('Pune', 'Mumbai', '32'),
        }[name]
        for fact in facts:
            assert fact.lower() in payload['answer'].lower(), (name, fact, payload['answer'])


def test_occupation_changes_chat_prose(monkeypatch):
    from app.chat import answer
    bundle = _bundle()
    farming = answer(ChatRequest(text='Will it rain today?', location=LOC, profile='farming'), bundle)['answer']
    tourism = answer(ChatRequest(text='Will it rain today?', location=LOC, profile='tourism'), bundle)['answer']
    fishing = answer(ChatRequest(text='Will it rain today?', location=LOC, profile='fishing'), bundle)['answer']
    assert farming != tourism != fishing
    assert 'agricultural' in farming.lower() or 'spray' in farming.lower() or 'farm' in farming.lower()
    assert 'clearance' in fishing.lower() or 'imd' in fishing.lower()
    assert 'outdoor' in tourism.lower() or 'uv' in tourism.lower() or 'window' in tourism.lower() or 'rain chance' in tourism.lower()


def test_bengali_forecast_uses_deterministic_template():
    from app.chat import answer
    result = answer(ChatRequest(text='Will it rain today?', location=LOC, language='bn'), _bundle())
    assert result['language'] == 'bn'
    assert 'তাপমাত্রা' in result['answer']
    assert '18' in result['answer'] and '°C' in result['answer']
    assert 'Conditions appear generally suitable' not in result['answer']


def test_hindi_forecast_does_not_append_english_recommendations():
    from app.chat import answer
    result = answer(ChatRequest(text='क्या आज बारिश होगी?', location=LOC, language='hi', profile='farming'), _bundle())
    assert result['language'] == 'hi'
    assert 'तापमान' in result['answer']
    assert 'Conditions appear generally suitable' not in result['answer']
    assert 'Check official warnings' not in result['answer']
    assert 'looks more workable' not in result['answer']
    assert 'Rain chance stays' not in result['answer']
    assert 'छिड़काव' in result['answer'] or 'खेत' in result['answer']


def test_active_alerts_none_uses_language_pack():
    from app.chat_tools import render_tool_result
    from app.tools import ToolResult
    result = ToolResult(data=[], retrieved_at=NOW.isoformat(), is_stale=False, sources=['imd'], status='available')
    payload = render_tool_result('get_active_alerts', result, ChatRequest(text='चेतावनी', location=LOC, language='hi'))
    assert payload['language'] == 'hi'
    assert 'The connected official service' not in payload['answer']
    assert 'चेतावनी' in payload['answer'] or 'सक्रिय' in payload['answer']


def test_production_example_questions_execute_user_facing_tools(monkeypatch):
    alerts = [{
        'headline': 'Heat wave warning', 'severity': 'moderate',
        'instruction': 'Stay hydrated', 'expires': '2099-01-01T00:00:00Z',
    }]
    client = _patch_chat_backends(monkeypatch, alerts=alerts)
    saved = [DELHI.model_dump(mode='json'), CHANDIGARH.model_dump(mode='json')]
    cases = [
        ('What is the weather now?', 'get_current_weather', ('18', '°C')),
        ('Will it rain between 3 and 6?', 'get_hourly_forecast', ('40', '%')),
        ('What about tomorrow?', 'get_daily_forecast', ('2026-09-12', '32', '55')),
        ('Any alerts near me?', 'get_active_alerts', ('Heat wave warning', 'Stay hydrated')),
        ("What's my weather score?", 'get_weather_score', ('82', 'Good conditions')),
        ('Compare Delhi and Chandigarh tomorrow.', 'compare_locations', ('Delhi', 'Chandigarh', '32')),
        ('What are the sea conditions?', 'get_marine_forecast', ('1.2', 'm')),
        ('Has Delhi become hotter over the last decade?', 'get_climate_summary', ('+0.2', 'ERA5')),
        ('What are my saved locations?', 'get_saved_locations', ('Delhi', 'Chandigarh')),
        ('Set a rain alert.', 'set_alert_rule', ('rain', 'saved')),
        ('What is the farming advisory?', 'get_agromet_advisory', ('not connected', 'Do not invent')),
    ]
    for text, tool, facts in cases:
        body = {
            'text': text,
            'location': LOC.model_dump(mode='json'),
            'saved_locations': saved,
        }
        response = client.post('/v1/chat/message', json=body)
        assert response.status_code == 200, (text, response.text)
        payload = response.json()
        assert payload['tool'] == tool, (text, payload['tool'], payload['answer'])
        for fact in facts:
            assert fact.lower() in payload['answer'].lower(), (text, fact, payload['answer'])


def test_compare_without_second_place_stays_honest(monkeypatch):
    client = _patch_chat_backends(monkeypatch)
    response = client.post('/v1/chat/message', json={
        'text': 'Compare Delhi and Chandigarh tomorrow.',
        'location': LOC.model_dump(mode='json'),
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload['tool'] == 'compare_locations'
    assert 'second' in payload['answer'].lower()
    assert '18.52' not in payload['answer']


def test_chat_tool_debug_trace_omits_user_text_and_coordinates(monkeypatch, caplog):
    import logging
    client = _patch_chat_backends(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger='weathergpt.chat'):
        response = client.post('/v1/chat/message', json={
            'text': 'Will it rain today at secret-query-text?',
            'location': {'name': 'Delhi', 'latitude': 28.6139, 'longitude': 77.209, 'timezone': 'Asia/Kolkata'},
        })
    assert response.status_code == 200
    assert response.json()['tool'] == 'get_current_weather'
    records = [record.getMessage() for record in caplog.records if record.name == 'weathergpt.chat']
    assert records
    joined = '\n'.join(records)
    assert 'chat_tool intent=' in joined
    assert 'tool=get_current_weather' in joined
    assert 'duration_ms=' in joined
    assert 'status=available' in joined
    assert 'secret-query-text' not in joined
    assert '28.6139' not in joined
    assert '77.209' not in joined


def test_keyword_router_still_selects_weather_score(monkeypatch):
    client = _patch_chat_backends(monkeypatch)
    response = client.post('/v1/chat/message', json={
        'text': 'What is my weather score for farming?',
        'location': LOC.model_dump(mode='json'),
        'profile': 'farming',
    })
    payload = response.json()
    assert payload['tool'] == 'get_weather_score'
    assert 'Weather score' in payload['answer'] or '82' in payload['answer'] or '70' in payload['answer']


def test_plain_weather_uses_deterministic_path_when_groq_off(monkeypatch):
    client = _patch_chat_backends(monkeypatch)
    response = client.post('/v1/chat/message', json={
        'text': 'Will it rain today?',
        'location': LOC.model_dump(mode='json'),
    })
    assert response.json()['tool'] == 'get_current_weather'
    assert response.json().get('response_origin') in {None, 'deterministic_fallback'}
