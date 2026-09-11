import asyncio
import json
import re
import time
from collections import deque
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from .metrics import metrics
from .models import Settings
from .security import sanitize_gemini_question


class PolishedAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)


class ToolChoice(BaseModel):
    tool: str = Field(min_length=1, max_length=80)


_TOOL_CHOICE_PROMPT = (
    'Pick exactly one WeatherGPT tool name for this sanitized user intent. '
    'Do not invent weather values, scores, warnings, or locations. '
    'Return JSON {"tool": "<name>"} using only an allowlisted name.'
)


FACT_MARKERS = (
    ' · ', 'Temperature:', 'तापमान', 'Highest hourly', 'बारिश की', 'Highest wind', 'हवा की',
    'Official warning', 'आधिकारिक चेतावनी', 'Severity:', 'Expires:', 'Highest significant',
    'Longest mean', 'ERA5', 'Data coverage', 'Comparing verified', ': high ',
    'Weather score', 'Channels:', 'Local alert rule', 'looks more workable', 'Rain chance',
    'Forecast agreement', 'Official warning takes precedence', 'local time',
    'Thunderstorm codes', 'This is a forecast, not a certainty', 'not a clearance',
    'does not mean there are no warnings', 'Weather sources disagree', 'spray window',
    'cached weather',
)
_BOILERPLATE = (
    'check official warnings before going out.',
    'बाहर जाने से पहले आधिकारिक चेतावनी देखें।',
)


def split_immutable(draft: str) -> tuple[str, str]:
    """Separate protected weather facts from rewordable prose."""
    facts: list[str] = []
    prose: list[str] = []
    for line in draft.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        numeric_fact = any(unit in stripped for unit in ('°C', '%', 'km/h', ' m', 'mm', 'किमी')) and any(ch.isdigit() for ch in stripped)
        if numeric_fact or any(marker in stripped for marker in FACT_MARKERS):
            facts.append(stripped)
        else:
            prose.append(stripped)
    return '\n'.join(facts), '\n'.join(prose)


def should_polish(prose: str) -> bool:
    cleaned = prose.strip().lower()
    if not cleaned:
        return False
    lines = [line.strip().lower() for line in prose.splitlines() if line.strip()]
    leftover = [line for line in lines if line not in _BOILERPLATE and not any(item in line for item in _BOILERPLATE)]
    return bool(leftover)


def validate_translation(draft: str, candidate: str) -> bool:
    """Numbers and units must survive translation. English severity words need not."""
    draft_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', draft))
    candidate_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', candidate))
    if candidate_numbers != draft_numbers:
        return False
    unit_pattern = r'(?<![\w])([-+]?\d+(?:\.\d+)?)\s*(°C|%|mm|m/s|km/h|m|seconds?|years?)(?!\w)'
    draft_units = {(number, unit.lower()) for number, unit in re.findall(unit_pattern, draft, re.IGNORECASE)}
    candidate_units = {(number, unit.lower()) for number, unit in re.findall(unit_pattern, candidate, re.IGNORECASE)}
    return draft_units == candidate_units


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
    draft_lower = draft.lower()
    protected_terms=('imd','incois','open-meteo','ecmwf','weathergpt risk estimate','official warning')
    if any(term in draft_lower and term not in lowered for term in protected_terms):
        return False
    if any(term in lowered and term not in draft_lower for term in protected_terms):
        return False
    severities=('yellow','orange','red','minor','moderate','severe','extreme')
    if {term for term in severities if term in draft_lower} != {term for term in severities if term in lowered}:
        return False
    if re.search(r'\bno (?:active |weather )?warnings?\b', lowered):
        return False
    invented_warning = re.search(r'\b(evacuate|cyclone|tsunami|red alert)\b', lowered)
    if invented_warning and not re.search(invented_warning.group(0), draft_lower):
        return False
    return True


class GeminiPolisher:
    def __init__(self, settings: Settings | None = None, max_calls_per_minute: int = 30):
        self.settings = settings or Settings()
        self.system = (Path(__file__).parents[1] / 'ai' / 'prompts' / 'weather_assistant.md').read_text(encoding='utf-8')
        self.max_calls_per_minute = max_calls_per_minute
        self._calls: deque[float] = deque()
        self._cooldown_until = 0.0
        self._quota_exhausted = False

    @property
    def enabled(self): return bool(self.settings.gemini_api_key and self.settings.gemini_model)

    def _budget_available(self) -> bool:
        now = time.monotonic()
        while self._calls and self._calls[0] < now - 60:
            self._calls.popleft()
        return len(self._calls) < self.max_calls_per_minute

    def _circuit_open(self) -> bool:
        return self._quota_exhausted or time.monotonic() < self._cooldown_until

    def _trip(self, seconds: float, quota: bool = False) -> None:
        self._cooldown_until = time.monotonic() + seconds
        if quota:
            self._quota_exhausted = True

    async def polish(self, question: str, draft: str, language: str, attempts: int = 2) -> str:
        """Reword only permitted prose. Protected facts stay deterministic.

        Transient 500/502/503/504 responses are retried once. HTTP 429, quota
        exhaustion and timeouts open a cooldown and return the draft so the
        demo never burns extra Gemini quota.
        """
        if not self.enabled or self._circuit_open() or not self._budget_available():
            metrics.inc('gemini_skipped')
            return draft
        facts, prose = split_immutable(draft)
        if not facts or not should_polish(prose):
            metrics.inc('gemini_skipped')
            return draft
        metrics.inc('gemini_calls')
        safe_question = sanitize_gemini_question(question)
        visible = (
            f'Language: {language}\n'
            f'User intent (coordinates redacted if present): {safe_question}\n'
            'IMMUTABLE FACTS — copy numbers, units, timestamps, source names and alert severity exactly if mentioned:\n'
            f'{facts or "(none)"}\n'
            'REWORDABLE TEXT — rewrite only this prose. Do not add weather numbers, warnings or sources:\n'
            f'{prose}'
        )
        payload = {
            'system_instruction': {'parts':[{'text':self.system}]},
            'contents':[{'role':'user','parts':[{'text':visible}]}],
            'generationConfig': {'temperature':0.1,'maxOutputTokens':700,'responseMimeType':'application/json',
                'responseSchema':{'type':'OBJECT','properties':{'answer':{'type':'STRING'}},'required':['answer']}}
        }
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent'
        for attempt in range(max(1,attempts)):
            self._calls.append(time.monotonic())
            try:
                async with httpx.AsyncClient(timeout=18,follow_redirects=False) as client:
                    response=await client.post(url,headers={'x-goog-api-key':self.settings.gemini_api_key},json=payload)
                    response.raise_for_status()
                raw=response.json()['candidates'][0]['content']['parts'][0]['text']
                candidate=PolishedAnswer.model_validate(json.loads(raw)).answer.strip()
                combined_draft = '\n'.join(part for part in (facts, prose) if part)
                combined_candidate = '\n'.join(part for part in (facts, candidate) if part)
                return combined_candidate if validate_polish(combined_draft, combined_candidate) else draft
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429:
                    self._trip(300, quota=True)
                    return draft
                retryable=error.response.status_code in (500,502,503,504)
                if not retryable or attempt+1>=max(1,attempts) or not self._budget_available():
                    if error.response.status_code in (503,504):
                        self._trip(60)
                    return draft
                await asyncio.sleep(0.6)
            except httpx.TimeoutException:
                self._trip(60)
                return draft
            except (httpx.HTTPError,KeyError,IndexError,ValueError,TypeError,json.JSONDecodeError):
                return draft
        return draft

    async def choose_tool(self, question: str, allowlist: tuple[str, ...] | list[str], fallback: str) -> str:
        """Map sanitized intent to an allowlisted tool. Never returns weather values."""
        allowed = tuple(name for name in allowlist if name)
        if not allowed or fallback not in allowed:
            return fallback
        if not self.enabled or self._circuit_open() or not self._budget_available():
            metrics.inc('gemini_skipped')
            return fallback
        metrics.inc('gemini_calls')
        names = ', '.join(allowed)
        safe_question = sanitize_gemini_question(question)
        visible = (
            f'{_TOOL_CHOICE_PROMPT}\n'
            f'Allowlisted tools: {names}\n'
            f'Intent (coordinates redacted if present): {safe_question}'
        )
        payload = {
            'system_instruction': {'parts': [{'text': self.system}]},
            'contents': [{'role': 'user', 'parts': [{'text': visible}]}],
            'generationConfig': {
                'temperature': 0,
                'maxOutputTokens': 64,
                'responseMimeType': 'application/json',
                'responseSchema': {
                    'type': 'OBJECT',
                    'properties': {'tool': {'type': 'STRING', 'enum': list(allowed)}},
                    'required': ['tool'],
                },
            },
        }
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent'
        self._calls.append(time.monotonic())
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                response = await client.post(url, headers={'x-goog-api-key': self.settings.gemini_api_key}, json=payload)
                response.raise_for_status()
            raw = response.json()['candidates'][0]['content']['parts'][0]['text']
            chosen = ToolChoice.model_validate(json.loads(raw)).tool.strip()
            return chosen if chosen in allowed else fallback
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 429:
                self._trip(300, quota=True)
            elif error.response.status_code in (503, 504):
                self._trip(60)
            return fallback
        except httpx.TimeoutException:
            self._trip(60)
            return fallback
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError):
            return fallback


gemini_polisher=GeminiPolisher()
