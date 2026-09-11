from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.chat import PHRASES, SUPPORTED_LANGUAGES, answer, phrase
from app.language import BhashiniProvider, GoogleTranslationProvider, LanguageService
from app.models import ChatRequest, Location, Settings


LOC = Location(name='Pune', latitude=18.52, longitude=73.85)
NOW = datetime(2026, 9, 11, 6, 0, tzinfo=timezone.utc)
NATIVE_RAIN = {
    'en': 'Will it rain today?',
    'hi': 'क्या आज बारिश होगी?',
    'bn': 'আজ কি বৃষ্টি হবে?',
    'te': 'ఈ రోజు వర్షం పడుతుందా?',
    'mr': 'आज पाऊस पडेल का?',
    'ta': 'இன்று மழை பெய்யுமா?',
    'gu': 'આજે વરસાદ પડશે?',
    'kn': 'ಇಂದು ಮಳೆ ಬರುತ್ತದೆಯೇ?',
    'ml': 'ഇന്ന് മഴ പെയ്യുമോ?',
    'pa': 'ਕੀ ਅੱਜ ਮੀਂਹ ਪਵੇਗਾ?',
    'or': 'ଆଜି ବର୍ଷା ହେବ କି?',
}
TEMP_MARKERS = {
    'en': 'Temperature', 'hi': 'तापमान', 'bn': 'তাপমাত্রা', 'te': 'ఉష్ణోగ్రత',
    'mr': 'तापमान', 'ta': 'வெப்பநிலை', 'gu': 'તાપમાન', 'kn': 'ತಾಪಮಾನ',
    'ml': 'താപനില', 'pa': 'ਤਾਪਮਾਨ', 'or': 'ତାପମାତ୍ରା',
}


def _bundle():
    hours = []
    for index in range(24):
        hours.append({
            'time': (NOW + timedelta(hours=index)).isoformat(),
            'temperature': 18 + index * 0.5,
            'rain_chance': 40,
            'wind_ms': 3.3,
            'humidity': 60,
        })
    return {
        'hourly': hours, 'is_stale': False, 'retrieved_at': NOW.isoformat(),
        'sources': ['open-meteo'], 'agreement': 'single_source',
        'official_status': 'available', 'alerts_status': 'available', 'official_alerts': [], 'alerts': [],
    }


@pytest.fixture
def freeze_chat_now(monkeypatch):
    from datetime import datetime as real_datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW

    monkeypatch.setattr('app.chat.datetime', FrozenDateTime)


def test_phrase_pack_covers_every_language_and_key():
    required = set(SUPPORTED_LANGUAGES)
    assert required == set(NATIVE_RAIN)
    for key, pack in PHRASES.items():
        missing = required - set(pack)
        assert not missing, (key, missing)
        for language in required:
            assert pack[language].strip(), (key, language)


@pytest.mark.parametrize('language', SUPPORTED_LANGUAGES)
def test_every_language_gets_a_deterministic_weather_conversation(language, freeze_chat_now):
    result = answer(ChatRequest(text=NATIVE_RAIN[language], location=LOC, language=language), _bundle())
    assert result['language'] == language
    assert TEMP_MARKERS[language] in result['answer']
    assert '18' in result['answer'] and '°C' in result['answer']
    assert '40' in result['answer'] and '%' in result['answer']
    if language != 'en':
        assert 'Conditions appear generally suitable' not in result['answer']


@pytest.mark.parametrize('language', SUPPORTED_LANGUAGES)
def test_alert_wrapper_keeps_severity_and_headline(language, freeze_chat_now):
    bundle = {
        **_bundle(),
        'official_alerts': [{
            'headline': 'Heat wave warning', 'severity': 'severe',
            'instruction': 'Stay hydrated', 'expires': '2099-01-01T00:00:00Z',
        }],
    }
    result = answer(ChatRequest(text='Any alerts near me?', location=LOC, language=language), bundle)
    assert result['language'] == language
    assert 'Heat wave warning' in result['answer']
    assert 'severe' in result['answer']
    assert 'Stay hydrated' in result['answer']
    assert '2099-01-01T00:00:00Z' in result['answer']


def test_live_translation_is_not_claimed_without_credentials(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.delenv('BHASHINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_TRANSLATE_API_KEY', raising=False)
    body = TestClient(app).get('/v1/languages/capabilities').json()
    assert body['answer_languages'] == list(SUPPORTED_LANGUAGES)
    assert body['answer_mode'] == 'deterministic_templates'
    assert body['live_translation'] is False or isinstance(body['live_translation'], bool)
    if not any(item.get('enabled') for item in body['providers']):
        assert body['live_translation'] is False
    assert 'deterministic' in body['fallback']['translation']


def test_every_language_chat_endpoint_uses_selected_language(monkeypatch, freeze_chat_now):
    from fastapi.testclient import TestClient
    from app import chat_tools, main
    from app.main import app

    async def weather(_):
        return _bundle()

    async def official(_):
        return {'status': 'available', 'alerts': [], 'message': 'available'}

    monkeypatch.setattr(chat_tools.service, 'bundle', weather)
    monkeypatch.setattr(main.service, 'bundle', weather)
    monkeypatch.setattr('app.tools.service.bundle', weather)
    monkeypatch.setattr(chat_tools.alert_service, 'official', official)
    monkeypatch.setattr(main.alert_service, 'official', official)

    async def keep_deterministic(_question, _allowlist, fallback):
        return fallback

    monkeypatch.setattr(chat_tools.gemini_polisher, 'choose_tool', keep_deterministic)
    client = TestClient(app)
    for language, text in NATIVE_RAIN.items():
        response = client.post('/v1/chat/message', json={
            'text': text, 'language': language, 'location': LOC.model_dump(mode='json'),
        })
        assert response.status_code == 200, (language, response.text)
        payload = response.json()
        assert payload['language'] == language
        assert payload['tool'] == 'get_current_weather'
        assert TEMP_MARKERS[language] in payload['answer']
        assert '18' in payload['answer'] and '40' in payload['answer']


def test_translation_validator_blocks_number_changes():
    from app.ai import validate_translation
    draft = phrase('en', 'temperature', lo=18, hi=29.5) + ' ' + phrase('en', 'rain', value=40)
    good = phrase('or', 'temperature', lo=18, hi=29.5) + ' ' + phrase('or', 'rain', value=40)
    bad = phrase('or', 'temperature', lo=21, hi=29.5) + ' ' + phrase('or', 'rain', value=40)
    assert validate_translation(draft, good)
    assert not validate_translation(draft, bad)



@pytest.mark.asyncio
async def test_bhashini_translation_contract():
    async def handler(request):
        body=__import__('json').loads(request.content)
        assert body['pipelineTasks'][0]['taskType']=='translation'
        assert request.headers['userid']=='user'
        return httpx.Response(200,json={'pipelineResponse':[{'output':[{'target':'बारिश'}]}]})
    settings=Settings(bhashini_compute_url='https://example.test/compute',bhashini_api_key='key',bhashini_user_id='user',bhashini_translation_service_id='service')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await BhashiniProvider(client,settings).translate('rain','en','hi')=='बारिश'


@pytest.mark.asyncio
async def test_google_translation_contract():
    async def handler(request):
        assert request.url.params['key']=='key'
        return httpx.Response(200,json={'data':{'translations':[{'translatedText':'बारिश'}]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await GoogleTranslationProvider(client,Settings(google_translate_api_key='key')).translate('rain','en','hi')=='बारिश'


@pytest.mark.asyncio
async def test_unconfigured_language_service_keeps_original(monkeypatch):
    monkeypatch.delenv('BHASHINI_API_KEY',raising=False);monkeypatch.delenv('GOOGLE_TRANSLATE_API_KEY',raising=False)
    result=await LanguageService().translate('Weather unavailable','en','or')
    assert result=={'text':'Weather unavailable','provider':'original','fallback':True}


def test_translate_endpoint_falls_back_without_credentials():
    from fastapi.testclient import TestClient
    from app.main import app
    response = TestClient(app).post('/v1/translate', json={'text': 'Rain tomorrow', 'source': 'en', 'target': 'hi'})
    assert response.status_code == 200
    body = response.json()
    assert body['text'] == 'Rain tomorrow'
    assert body['fallback'] is True


def test_voice_endpoints_are_honestly_disabled():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    assert client.post('/v1/voice/transcribe').status_code == 501
    assert client.post('/v1/voice/synthesize').status_code == 501


@pytest.mark.asyncio
async def test_agromet_tool_is_explicitly_unavailable():
    from app.models import Location
    from app.tools import AgrometInput, get_agromet_advisory
    result = await get_agromet_advisory(AgrometInput(location=Location(name='Delhi', latitude=28.6, longitude=77.2)))
    assert result.status == 'unavailable'
    assert 'agromet' in (result.error or '').lower()
