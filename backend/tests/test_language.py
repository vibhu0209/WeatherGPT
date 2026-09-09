import httpx
import pytest

from app.language import BhashiniProvider, GoogleTranslationProvider, LanguageService
from app.models import Settings


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
