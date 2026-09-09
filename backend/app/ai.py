import json
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from .models import Settings


class PolishedAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


def validate_polish(draft: str, candidate: str) -> bool:
    draft_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', draft))
    candidate_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', candidate))
    if candidate_numbers != draft_numbers:
        return False
    unit_pattern=r'(?<![\w])([-+]?\d+(?:\.\d+)?)\s*(°C|%|mm|m/s|km/h|m|seconds?|years?)(?!\w)'
    draft_units={(number,unit.lower()) for number,unit in re.findall(unit_pattern,draft,re.IGNORECASE)}
    candidate_units={(number,unit.lower()) for number,unit in re.findall(unit_pattern,candidate,re.IGNORECASE)}
    if candidate_units != draft_units:
        return False
    lowered = candidate.lower()
    protected_terms=('imd','incois','open-meteo','ecmwf','weathergpt risk estimate','official warning')
    if any(term in draft.lower() and term not in lowered for term in protected_terms):
        return False
    severities=('yellow','orange','red','minor','moderate','severe','extreme')
    if {term for term in severities if term in draft.lower()} != {term for term in severities if term in lowered}:
        return False
    if re.search(r'\bno (?:active |weather )?warnings?\b', lowered):
        return False
    return True


class GeminiPolisher:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.system = (Path(__file__).parents[1] / 'ai' / 'prompts' / 'weather_assistant.md').read_text(encoding='utf-8')

    @property
    def enabled(self): return bool(self.settings.gemini_api_key and self.settings.gemini_model)

    async def polish(self, question: str, draft: str, language: str) -> str:
        if not self.enabled:
            return draft
        payload = {
            'system_instruction': {'parts':[{'text':self.system}]},
            'contents':[{'role':'user','parts':[{'text':f'Language: {language}\nQuestion: {question}\nVerified draft:\n{draft}'}]}],
            'generationConfig': {'temperature':0.1,'maxOutputTokens':700,'responseMimeType':'application/json',
                'responseSchema':{'type':'OBJECT','properties':{'answer':{'type':'STRING'}},'required':['answer']}}
        }
        try:
            url=f'https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent'
            async with httpx.AsyncClient(timeout=18,follow_redirects=False) as client:
                response=await client.post(url,headers={'x-goog-api-key':self.settings.gemini_api_key},json=payload)
                response.raise_for_status()
            raw=response.json()['candidates'][0]['content']['parts'][0]['text']
            candidate=PolishedAnswer.model_validate(json.loads(raw)).answer.strip()
            return candidate if validate_polish(draft,candidate) else draft
        except (httpx.HTTPError,KeyError,IndexError,ValueError,TypeError,json.JSONDecodeError):
            return draft


gemini_polisher=GeminiPolisher()


