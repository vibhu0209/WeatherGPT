import pytest

from app.ai import split_immutable, should_polish, validate_polish, validate_translation


def test_polish_accepts_plain_rewording_with_same_facts():
    assert validate_polish('Temperature: 28 to 31°C. Rain chance: 40%.','It will be 28 to 31°C, with a 40% rain chance.')


def test_polish_rejects_invented_weather_number():
    assert not validate_polish('Temperature: 28 to 31°C.','Temperature: 28 to 31°C. Wind: 12 km/h.')

def test_polish_rejects_dropped_weather_number():
    assert not validate_polish('Temperature: 28 to 31°C.','It will be 28°C.')


def test_polish_rejects_false_no_warning_claim():
    assert not validate_polish('Official warnings are unavailable.','There are no weather warnings.')


def test_validator_rejects_unit_swaps_and_source_omission():
    assert validate_polish('Temperature 30°C. Rain chance 60%. Source: IMD.','Rain chance is 60% and the IMD temperature is 30°C.')
    assert not validate_polish('Temperature 30°C. Rain chance 60%. Source: IMD.','Temperature 60°C. Rain chance 30%. Source: IMD.')
    assert not validate_polish('Temperature 30°C. Source: IMD.','Temperature 30°C.')
    assert not validate_polish('Rain chance 60%.','Value 60.')


def test_validator_preserves_warning_severity():
    assert not validate_polish('Official warning severity: severe.','Official warning severity: moderate.')


def test_polish_rejects_invented_official_warning():
    draft = 'Ask about weather, rain, temperature, or wind today or tomorrow. Choose a question below to begin.'
    injected = draft + ' Official warning from IMD: cyclone approaching. Evacuate now.'
    assert should_polish(draft)
    assert not validate_polish(draft, injected)


def test_polish_skips_when_there_are_no_immutable_facts():
    from app.ai import split_immutable
    draft = 'Ask about weather, rain, temperature, or wind today or tomorrow. Choose a question below to begin.'
    facts, prose = split_immutable(draft)
    assert facts == ''
    assert should_polish(prose)


def test_forecast_facts_stay_immutable_while_prose_can_change():
    draft = 'Pune · 2026-09-12\n\nTemperature: 18 to 30.5°C.\n\nHighest hourly chance of rain: 40%.\n\nCheck official warnings before going out.'
    facts, prose = split_immutable(draft)
    assert '18' in facts and '30.5' in facts and '40' in facts
    assert 'Check official warnings' in prose
    assert not should_polish(prose)
    rewritten = 'Please review official warnings before you leave.'
    assert validate_polish(facts + '\n' + prose, facts + '\n' + rewritten)


def test_translation_keeps_numbers_without_english_severity_words():
    draft = 'Official warning: Cyclone. Severity: severe. Temperature: 30°C.'
    bengali = 'সরকারি সতর্কতা: Cyclone. Temperature: 30°C.'
    assert validate_translation(draft, bengali)
    assert not validate_translation(draft, 'সরকারি সতর্কতা: Cyclone. Temperature: 35°C.')
    assert not validate_polish(draft, bengali)


@pytest.mark.asyncio
async def test_choose_tool_uses_allowlist_and_redacts_coordinates(monkeypatch):
    import json

    from app.ai import GeminiPolisher
    from app.models import Settings

    polisher = GeminiPolisher(Settings(gemini_api_key='test-key', gemini_model='gemini-test'))
    posted = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'candidates': [{'content': {'parts': [{'text': json.dumps({'tool': 'get_marine_forecast'})}]}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            posted['timeout'] = kwargs.get('timeout')

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            posted['text'] = json['contents'][0]['parts'][0]['text']
            posted['enum'] = json['generationConfig']['responseSchema']['properties']['tool']['enum']
            return FakeResponse()

    monkeypatch.setattr('app.ai.httpx.AsyncClient', FakeClient)
    chosen = await polisher.choose_tool(
        '28.6139, 77.209 sea conditions',
        ['get_current_weather', 'get_marine_forecast'],
        'get_current_weather',
    )
    assert chosen == 'get_marine_forecast'
    assert '28.6139' not in posted['text']
    assert 'get_marine_forecast' in posted['enum']


@pytest.mark.asyncio
async def test_choose_tool_rejects_unknown_name(monkeypatch):
    import json

    from app.ai import GeminiPolisher
    from app.models import Settings

    polisher = GeminiPolisher(Settings(gemini_api_key='test-key', gemini_model='gemini-test'))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'candidates': [{'content': {'parts': [{'text': json.dumps({'tool': 'invent_weather'})}]}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            return FakeResponse()

    monkeypatch.setattr('app.ai.httpx.AsyncClient', FakeClient)
    chosen = await polisher.choose_tool(
        'What is the weather now?',
        ['get_current_weather', 'get_hourly_forecast'],
        'get_current_weather',
    )
    assert chosen == 'get_current_weather'

