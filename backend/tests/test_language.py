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
