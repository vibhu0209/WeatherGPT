"""LLM-neutral validators and retired Gemini polish stubs.

Active conversational reasoning uses Groq (`groq_orchestrator`). Gemini is not
called at runtime. Validators remain for translation and grounded-answer checks.
"""
from __future__ import annotations

import logging
import re

from .models import Settings

_log = logging.getLogger('weathergpt.ai')


FACT_MARKERS = (
    'Official warning', 'आधिकारिक चेतावनी', 'Severity:', 'Expires:',
    'ERA5', 'Data coverage', 'Comparing verified',
    'Channels:', 'Local alert rule',
)
_FACT_PREFIXES = (
    'Temperature:', 'तापमान', 'Highest hourly', 'बारिश की', 'Highest wind', 'हवा की',
    'Highest significant', 'Longest mean', 'Weather score', 'Rain chance',
    'Forecast agreement',
)
_BOILERPLATE = (
    'check official warnings before going out.',
    'if an imd warning is active for your area, follow that first.',
    'बाहर जाने से पहले आधिकारिक चेतावनी देखें।',
    'अगर आपके क्षेत्र में imd की आधिकारिक चेतावनी हो, तो पहले वही मानें।',
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
        header_fact = ' · ' in stripped and any(ch.isdigit() for ch in stripped)
        marker_fact = any(marker in stripped for marker in FACT_MARKERS) or stripped.startswith(_FACT_PREFIXES)
        if numeric_fact or header_fact or marker_fact:
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
    """Provider-neutral LLM response validator (strict equality of weather facts)."""
    draft_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', draft))
    candidate_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', candidate))
    if candidate_numbers != draft_numbers:
        return False
    unit_pattern = r'(?<![\w])([-+]?\d+(?:\.\d+)?)\s*(°C|%|mm|m/s|km/h|m|seconds?|years?)(?!\w)'
    draft_units = {(number, unit.lower()) for number, unit in re.findall(unit_pattern, draft, re.IGNORECASE)}
    candidate_units = {(number, unit.lower()) for number, unit in re.findall(unit_pattern, candidate, re.IGNORECASE)}
    if candidate_units != draft_units:
        return False
    lowered = candidate.lower()
    draft_lower = draft.lower()
    protected_terms = ('imd', 'incois', 'open-meteo', 'ecmwf', 'weathergpt risk estimate', 'official warning')
    if any(term in draft_lower and term not in lowered for term in protected_terms):
        return False
    if any(term in lowered and term not in draft_lower for term in protected_terms):
        return False
    severities = ('yellow', 'orange', 'red', 'minor', 'moderate', 'severe', 'extreme')
    if {term for term in severities if term in draft_lower} != {term for term in severities if term in lowered}:
        return False
    if re.search(r'\bno (?:active |weather )?warnings?\b', lowered):
        return False
    invented_warning = re.search(r'\b(evacuate|cyclone|tsunami|red alert)\b', lowered)
    if invented_warning and not re.search(invented_warning.group(0), draft_lower):
        return False
    return True


# Alias used by docs / newer call sites.
validate_llm_response = validate_polish


class GeminiPolisher:
    """Retired. Kept so older tests that construct the class still import cleanly.

    Never calls the Gemini API. polish()/choose_tool() are no-ops.
    """

    def __init__(self, settings: Settings | None = None, max_calls_per_minute: int = 30):
        self.settings = settings or Settings()
        self.max_calls_per_minute = max_calls_per_minute
        self._calls = []
        self._cooldown_until = 0.0
        self._quota_exhausted = False

    @property
    def enabled(self) -> bool:
        return False

    def _budget_available(self) -> bool:
        return False

    def _circuit_open(self) -> bool:
        return True

    def _trip(self, seconds: float, quota: bool = False) -> None:
        self._cooldown_until = seconds
        if quota:
            self._quota_exhausted = True

    async def polish(self, question: str, draft: str, language: str, attempts: int = 2) -> str:
        _log.info('gemini_attempt=false reason=retired result=skipped')
        return draft

    async def choose_tool(self, question: str, allowlist: tuple[str, ...] | list[str], fallback: str) -> str:
        _log.info('gemini_attempt=false reason=retired result=skipped')
        return fallback


gemini_polisher = GeminiPolisher()
