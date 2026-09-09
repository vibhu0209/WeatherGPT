"""Backend-only external language adapters with original-text fallback."""
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import httpx

from .models import Settings
from .security import assert_https_allowlisted


LANGUAGES = {'en','hi','bn','te','mr','ta','gu','kn','ml','pa','or'}


class LanguageProvider(ABC):
    id = ''
    def __init__(self, client: httpx.AsyncClient, settings: Settings): self.client,self.settings=client,settings
    @property
    @abstractmethod
    def enabled(self): ...
    @abstractmethod
    async def translate(self,text:str,source:str,target:str)->str: ...
    def health(self): return {'provider':self.id,'enabled':self.enabled,'capabilities':{'translation':True,'asr':False,'tts':False,'transliteration':False}}
    @staticmethod
    def validate(text,source,target):
        if not text or len(text)>4000: raise ValueError('Translation text must contain 1 to 4000 characters')
        if source not in LANGUAGES or target not in LANGUAGES: raise ValueError('Unsupported language')


class BhashiniProvider(LanguageProvider):
    id='bhashini'
    @property
    def enabled(self): return bool(self.settings.bhashini_compute_url and self.settings.bhashini_api_key and self.settings.bhashini_user_id and self.settings.bhashini_translation_service_id)
    def _allowed_hosts(self) -> set[str] | None:
        configured = {host.strip().lower() for host in (self.settings.bhashini_allowed_hosts or '').split(',') if host.strip()}
        if configured:
            return configured
        host = urlparse(self.settings.bhashini_compute_url).hostname
        return {host.lower()} if host else set()
    async def translate(self,text,source,target):
        self.validate(text,source,target)
        if not self.enabled: raise RuntimeError('BHASHINI is not configured')
        assert_https_allowlisted(self.settings.bhashini_compute_url, self._allowed_hosts())
        payload={'pipelineTasks':[{'taskType':'translation','config':{'language':{'sourceLanguage':source,'targetLanguage':target},'serviceId':self.settings.bhashini_translation_service_id}}],
            'inputData':{'input':[{'source':text}]}}
        response=await self.client.post(self.settings.bhashini_compute_url,headers={'Authorization':self.settings.bhashini_api_key,'userID':self.settings.bhashini_user_id},json=payload)
        response.raise_for_status()
        return response.json()['pipelineResponse'][0]['output'][0]['target']


class GoogleTranslationProvider(LanguageProvider):
    id='google-cloud-translation'
    @property
    def enabled(self): return bool(self.settings.google_translate_api_key)
    async def translate(self,text,source,target):
        self.validate(text,source,target)
        if not self.enabled: raise RuntimeError('Google Cloud Translation is not configured')
        response=await self.client.post('https://translation.googleapis.com/language/translate/v2',
            params={'key': self.settings.google_translate_api_key},
            json={'q':text,'source':source,'target':target,'format':'text'})
        response.raise_for_status()
        return response.json()['data']['translations'][0]['translatedText']


class LanguageService:
    async def translate(self,text,source,target):
        if source==target: return {'text':text,'provider':'original','fallback':False}
        settings=Settings()
        async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
            for provider in (BhashiniProvider(client,settings),GoogleTranslationProvider(client,settings)):
                if not provider.enabled: continue
                try: return {'text':await provider.translate(text,source,target),'provider':provider.id,'fallback':False}
                except (httpx.HTTPError,ValueError,KeyError,IndexError,RuntimeError): continue
        return {'text':text,'provider':'original','fallback':True}


language_service=LanguageService()
