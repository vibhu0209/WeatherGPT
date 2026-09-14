"""Deterministic tool selection and invocation for production chat."""
from __future__ import annotations

import asyncio
import logging
import time

import httpx

from .alerts import alert_service
from .chat import (
    TOMORROW_WORDS, answer, chat_language, format_official_warning, format_recommendation,
    grounded_advice_lines, mentions, parse_hour_window, phrase,
)
from .decision import recommendations
from .models import ChatRequest, Location, MS_TO_KMH
from .security import public_location, display_place_name
from .tools import (
    AlertRuleInput, AgrometInput, ClimateInput, CompareInput, DailyInput, HazardInput, MarineInput,
    ProviderStatusInput, SavedLocationsInput, ScoreInput, TOOL_REGISTRY, TimeRangeInput,
    ToolResult,
)
from .weather import service

USER_FACING_TOOLS = frozenset(TOOL_REGISTRY)
INTERNAL_TOOLS: frozenset[str] = frozenset()
_LOG = logging.getLogger('weathergpt.chat')


def _wants_alert_rule(text: str) -> bool:
    if any(token in text for token in ('notify me', 'alert rule', 'subscribe', 'notification rule')):
        return True
    if any(word in text for word in ('alert', 'notification')) and any(
        word in text for word in ('set ', 'create ', 'add ', 'enable ', 'turn on')
    ):
        return True
    return False


def _intent_for(request: ChatRequest, tool: str) -> str:
    text = request.text.lower()
    if tool == 'get_hourly_forecast' and parse_hour_window(text, request.location.timezone)[0] is not None:
        return 'hourly_window'
    if tool == 'get_daily_forecast' and mentions(text, TOMORROW_WORDS):
        return 'daily_tomorrow'
    if tool == 'compare_locations' and request.secondary_location is None:
        return 'compare_named_places'
    return tool


def select_tool(request: ChatRequest) -> str:
    text = request.text.lower()
    if request.secondary_location is not None:
        return 'compare_locations'
    if _wants_alert_rule(text):
        return 'set_alert_rule'
    window_start, _window_end = parse_hour_window(text, request.location.timezone)
    if window_start is not None:
        return 'get_hourly_forecast'
    if any(word in text for word in (
        'event', 'outdoor event', 'flood', 'waterlog', 'heavy rain', 'heavy rainfall',
        'downpour', 'cloudburst', 'why is', 'why are', 'why raining', 'radar',
    )):
        return 'get_hourly_forecast'
    # Emergency profile defaults to the multi-hazard board for open safety questions.
    if request.profile == 'emergency' and any(
        word in text for word in (
            'warning', 'alert', 'risk', 'safe', 'should', 'dashboard', 'situation',
            'road', 'rain', 'flood', 'what now', 'status', 'brief',
        )
    ):
        return 'get_disaster_briefing'
    rules = (
        ('compare_locations', ('compare', 'तुलना', ' vs ', 'versus')),
        ('get_marine_forecast', (
            'fish', 'marine', 'wave', 'harbour', 'harbor', 'sea', 'swell', 'coast', 'tide',
            'समुद्र', 'मछली', 'সমুদ্র', 'মাছ', 'సముద్ర', 'చేపల', 'मासे',
            'கடல்', 'மீன்', 'સમુદ્ર', 'માછી', 'ಸಮುದ್ರ', 'ಮೀನು', 'കടൽ', 'മത്സ്യ',
            'ਸਮੁੰਦਰ', 'ਮੱਛੀ', 'ସମୁଦ୍ର', 'ମାଛ',
        )),
        ('get_climate_summary', (
            'climate', 'hotter', 'years', 'monsoon', 'era5', 'decade',
            'जलवायु', 'साल', 'গরম', 'বছর', 'వేడి', 'సంవత్సర', 'उबदार', 'वर्षां',
            'சூட', 'ஆண்டு', 'ગરમ', 'વર્ષ', 'ಬಿಸಿ', 'ವರ್ಷ', 'ചൂട', 'വർഷ',
            'ਗਰਮ', 'ਸਾਲ', 'ଗରମ', 'ଜଳବାୟୁ',
        )),
        ('get_active_alerts', (
            'alert', 'warning', 'चेतावनी', 'সতর্কতা', 'హెచ్చరిక', 'इशारे',
            'எச்சரிக்கை', 'ચેતવણી', 'ಎಚ್ಚರಿಕೆ', 'മുന്നറിയിപ്പ്', 'ਚੇਤਾਵਨੀ', 'ଚେତାବନୀ',
        )),
        ('get_agromet_advisory', (
            'agromet', 'crop advisory', 'कृषि सलाह', 'farming advisory', 'farming advice',
            'crop advice', 'कृषि परामर्श',
        )),
        ('get_disaster_briefing', (
            'disaster briefing', 'disaster management', 'multi hazard', 'multi-hazard',
            'emergency dashboard', 'situation report', 'sitrep', 'relief camp', 'shelter',
            'evacuat', 'ndma', 'sachet', 'what should responders', 'disaster response',
            'आपदा', 'आपातकाल', 'निकासी',
        )),
        ('assess_infrastructure_hazard', (
            'landslide', 'landslip', 'mudslide', 'debris flow', 'slope failure',
            'road collapse', 'road cut', 'will the road', 'highway blocked', 'cut off',
            'भूस्खलन', 'सड़क', 'infrastructure risk', 'terrain angle', 'soil moisture',
            'gis', 'which roads', 'village cut',
        )),
        ('get_weather_score', (
            'score', 'should i', 'should we', 'can i', 'can we', 'is it safe', 'safe to',
            'good time', 'work outside', 'occupation', 'for me',
            'sow', 'sowing', 'seed', 'irrigat', 'spray', 'spraying',
            'drive', 'driving', 'walk', 'hiking', 'dry clothes', 'outdoors', 'outdoor',
            'travel', 'travelling', 'traveling', 'field work', 'go out',
            'खेत के काम', 'বাইরে', 'పని', 'काम', 'வெளியே',
            'kheti', 'खेती', 'best time', 'bahar kaam', 'बाहर काम',
            'बुआई', 'बीज', 'सिंचाई', 'छिड़काव',
        )),
        ('get_provider_status', ('provider', 'source', 'confidence', 'which model', 'disagreement')),
        ('get_saved_locations', ('saved location', 'saved place', 'my places', 'my locations')),
        ('get_hourly_forecast', (
            'hourly', 'hour by hour', 'next three hours', 'next 3 hours', 'अगले तीन घंटे',
            'shaam', 'subah', 'शाम', 'सुबह', 'evening', 'morning', 'baarish', 'बारिश',
            'will it rain', 'will rain', 'going to rain', 'rain today', 'rain tomorrow',
            'any rain', 'is it raining', 'वर्षा', 'ক्या बारिश',
        )),
        ('get_daily_forecast', (
            'daily', 'next days', 'this week', 'week ahead', *TOMORROW_WORDS,
        )),
    )

    for name, words in rules:
        if any(word in text for word in words):
            return name
    if 'advisory' in text and any(word in text for word in ('farm', 'crop', 'agromet', 'कृषि')):
        return 'get_agromet_advisory'
    return 'get_current_weather'


def _day_offset(request: ChatRequest) -> int:
    if mentions(request.text, TOMORROW_WORDS):
        return 1
    return request.day_offset


_SCORE_LABELS = {
    'Good conditions': 'score_good',
    'Moderate conditions': 'score_moderate',
    'Difficult conditions': 'score_difficult',
    'Unavailable': 'score_unavailable_label',
    'Marine safety score unavailable': 'score_marine_unavailable',
}


def _dedupe_places(places: list[Location]) -> list[Location]:
    unique: list[Location] = []
    seen: set[tuple[float, float]] = set()
    for place in places:
        key = (round(place.latitude, 4), round(place.longitude, 4))
        if key not in seen:
            seen.add(key)
            unique.append(place)
    return unique


def _compare_places(request: ChatRequest) -> list[Location]:
    text = request.text.lower()
    candidates: list[Location] = []
    if request.secondary_location is not None:
        candidates.append(request.location)
        candidates.append(request.secondary_location)
    for place in (request.location, *request.saved_locations):
        name = (place.name or '').strip().lower()
        if len(name) >= 2 and name in text:
            candidates.append(place)
    return _dedupe_places(candidates)[:4]


def _alert_channels(text: str) -> list[str]:
    lowered = text.lower()
    channels: list[str] = []
    if any(word in lowered for word in ('rain', 'बारिश', 'বৃষ্টি')):
        channels.append('rain')
    if any(word in lowered for word in ('severe', 'warning', 'extreme')):
        channels.append('severe')
    return channels or ['severe']


def _input_for(name: str, request: ChatRequest):
    location = request.location
    if name == 'get_current_weather':
        return location
    if name == 'get_hourly_forecast':
        start, end = parse_hour_window(request.text, request.location.timezone)
        return TimeRangeInput(location=location, start=start, end=end)
    if name == 'get_daily_forecast':
        return DailyInput(location=location, days=7)
    if name == 'get_active_alerts':
        return location
    if name == 'get_weather_score':
        return ScoreInput(location=location, profile=request.profile)  # type: ignore[arg-type]
    if name == 'get_climate_summary':
        metric = 'rainfall' if any(word in request.text.lower() for word in ('rain', 'monsoon', 'बारिश')) else 'temperature'
        return ClimateInput(location=location, metric=metric, years=10)
    if name == 'get_marine_forecast':
        return MarineInput(location=location, hours=48)
    if name == 'get_provider_status':
        return ProviderStatusInput()
    if name == 'compare_locations':
        unique = _compare_places(request)
        if len(unique) < 2:
            return None
        return CompareInput(locations=unique, day_offset=_day_offset(request))
    if name == 'get_saved_locations':
        return SavedLocationsInput(locations=request.saved_locations)
    if name == 'set_alert_rule':
        return AlertRuleInput(location=location, enabled=True, channels=_alert_channels(request.text))  # type: ignore[arg-type]
    if name == 'get_agromet_advisory':
        return AgrometInput(location=location)
    if name == 'assess_infrastructure_hazard':
        return HazardInput(location=location)
    if name == 'get_disaster_briefing':
        return HazardInput(location=location)
    raise KeyError(name)


def _missing_compare_result() -> ToolResult:
    from datetime import datetime, timezone
    return ToolResult(
        data={'comparisons': []},
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        is_stale=False,
        sources=[],
        status='unavailable',
        error='Name a second saved place to compare. WeatherGPT compares verified daily forecasts only.',
    )


async def invoke_registered_tool(name: str, request: ChatRequest) -> ToolResult:
    if name not in TOOL_REGISTRY:
        raise KeyError(name)
    payload = _input_for(name, request)
    if payload is None and name == 'compare_locations':
        return _missing_compare_result()
    _model, function = TOOL_REGISTRY[name]
    return await function(payload)


def context(request: ChatRequest, retrieved_at: str, intent: str) -> dict:
    return {
        'conversation_id': str(request.conversation_id),
        'resolved_location': public_location(request.location),
        'resolved_day_offset': request.day_offset,
        'profile': request.profile,
        'last_intent': intent,
        'last_weather_context_id': retrieved_at,
        'tool': intent,
    }


def _attach_tool(payload: dict, name: str) -> dict:
    payload['tool'] = name
    payload.setdefault('conversation_context', {})['tool'] = name
    payload['conversation_context']['last_intent'] = name
    return payload


def _trace(intent: str, tool: str, duration_ms: int, status: str) -> None:
    if _LOG.isEnabledFor(logging.DEBUG):
        _LOG.debug('chat_tool intent=%s tool=%s duration_ms=%s status=%s', intent, tool, duration_ms, status)


async def resolve_tool(request: ChatRequest) -> tuple[str, str]:
    """Deterministic keyword router. Groq orchestration happens in run_chat."""
    deterministic = select_tool(request)
    return _intent_for(request, deterministic), deterministic


async def _forecast_answer(request: ChatRequest, name: str) -> dict:
    data, official = await asyncio.gather(
        service.bundle(request.location),
        alert_service.official(request.location),
    )
    data = {
        **data,
        'official_status': official['status'],
        'alerts_status': official['status'],
        'official_alerts': official['alerts'],
        'alerts': official['alerts'],
    }
    return _attach_tool(answer(request, data), name)


async def _marine_answer(request: ChatRequest, result: ToolResult) -> dict:
    language = chat_language(request.language)
    official = await alert_service.official(request.location)
    facts: list[str] = []
    official_sources: list[str] = []
    if official['alerts']:
        for alert in official['alerts']:
            facts.append(format_official_warning(language, alert))
            if alert.get('sender'):
                official_sources.append(alert['sender'])
    elif official['status'] != 'available':
        facts.append(phrase(language, 'marine_unknown'))
    else:
        facts.append(phrase(language, 'marine_none'))
    data = result.data if isinstance(result.data, dict) else {}
    rows = (data.get('hourly') or [])[:24]
    waves = [row.get('wave_height_m') for row in rows if row.get('wave_height_m') is not None]
    periods = [row.get('wave_period_s') for row in rows if row.get('wave_period_s') is not None]
    facts.append(phrase(language, 'marine_intro', name=display_place_name(request.location.name)))
    if waves:
        facts.append(phrase(language, 'marine_wave', value=max(waves)))
    if periods:
        facts.append(phrase(language, 'marine_period', value=max(periods)))
    if request.profile == 'fishing':
        for rec in recommendations(
            [], 'fishing', rows, timezone_name=request.location.timezone,
            official_alerts=official['alerts'], official_status=official['status'],
            marine_available=True, sources=list(result.sources),
        ):
            line = format_recommendation(language, rec)
            if line and line not in facts:
                facts.append(line)
    facts.append(phrase(language, 'marine_disclaimer'))
    sources = list(result.sources) + list(dict.fromkeys(official_sources))
    return _attach_tool({
        'answer': '\n\n'.join(facts),
        'language': language,
        'day_offset': request.day_offset,
        'retrieved_at': result.retrieved_at,
        'is_stale': False,
        'sources': sources,
        'agreement': 'single_marine_model',
        'conversation_context': context(request, result.retrieved_at, 'get_marine_forecast'),
    }, 'get_marine_forecast')


def _render_hourly(result: ToolResult, request: ChatRequest) -> str:
    from .chat import is_action_question, is_rain_question, rain_decision_lead, parse_hour_window
    from .event_risk import (
        assess_timed_event_risk, clock_window_label, format_event_risk_answer,
        is_event_question, is_heavy_rain_or_flood_question, is_why_question, why_weather_brief,
    )

    rows = result.data if isinstance(result.data, list) else []
    language = chat_language(request.language)
    if not rows:
        return result.error or phrase(language, 'unavailable')
    temps = [row['temperature'] for row in rows if row.get('temperature') is not None]
    rain = [row['rain_chance'] for row in rows if row.get('rain_chance') is not None]
    wind = [row['wind_ms'] for row in rows if row.get('wind_ms') is not None]
    rain_max = max(rain) if rain else None
    why_line = why_weather_brief({
        'sources': list(result.sources or []),
        'source_count': len(result.sources or []),
    })
    event_like = is_event_question(request.text) or is_heavy_rain_or_flood_question(request.text)
    if event_like:
        start, end = parse_hour_window(request.text, request.location.timezone)
        label = clock_window_label(start, end) if start and end else 'this period'
        assessment = assess_timed_event_risk(
            rows, place=display_place_name(request.location.name), window_label=label,
        )
        return format_event_risk_answer(assessment, why_line=why_line, user_text=request.text)
    supporting = [f'{display_place_name(request.location.name)}']
    if rain:
        supporting.append(phrase(language, 'rain', value=max(rain)))
    if temps:
        supporting.append(phrase(language, 'temperature', lo=min(temps), hi=max(temps)))
    if wind and not is_rain_question(request.text):
        supporting.append(phrase(language, 'wind', value=max(wind) * MS_TO_KMH))
    if why_line and is_why_question(request.text):
        supporting.append(why_line)
    supporting.append(phrase(language, 'official'))
    if is_why_question(request.text):
        lead = rain_decision_lead(rain_max) if rain_max is not None else 'Here is what the verified hourly forecast supports.'
        return '\n\n'.join([lead, *supporting])
    if is_rain_question(request.text):
        return '\n\n'.join([rain_decision_lead(rain_max), *supporting])
    if not is_action_question(request.text):
        return '\n\n'.join(supporting)
    if rain_max is not None and rain_max >= 60:
        lead = 'Weather-wise, I would wait — rain risk is high in this window.'
    elif rain_max is not None and rain_max >= 35:
        lead = 'It is probably okay with some risk — keep plans flexible around rain timing.'
    else:
        lead = 'Weather-wise, conditions look reasonably suitable in this window.'
    return '\n\n'.join([lead, *supporting])


def _render_daily(result: ToolResult, request: ChatRequest) -> str:
    from .chat import is_rain_question, rain_decision_lead

    rows = result.data if isinstance(result.data, list) else []
    language = chat_language(request.language)
    if not rows:
        return result.error or phrase(language, 'unavailable')
    offset = min(_day_offset(request), len(rows) - 1)
    day = rows[offset]
    lo = day.get('temperature_min') if day.get('temperature_min') is not None else day.get('temperature_max')
    hi = day.get('temperature_max')
    rain_max = day.get('rain_chance_max')
    parts: list[str] = []
    if is_rain_question(request.text):
        parts.append(rain_decision_lead(rain_max))
    parts.append(f"{display_place_name(request.location.name)} · {day.get('date')}")
    if rain_max is not None:
        parts.append(phrase(language, 'rain', value=rain_max))
    if lo is not None and hi is not None:
        parts.append(phrase(language, 'temperature', lo=lo, hi=hi))
    elif hi is not None:
        parts.append(phrase(language, 'temperature', lo=hi, hi=hi))
    if day.get('wind_max_ms') is not None and not is_rain_question(request.text):
        parts.append(phrase(language, 'wind', value=day['wind_max_ms'] * MS_TO_KMH))
    parts.append(phrase(language, 'official'))
    return '\n\n'.join(parts)


def _score_label(language: str, label: str) -> str:
    key = _SCORE_LABELS.get(label)
    return phrase(language, key) if key else label


def _action_lead_and_tip(text: str, score: int | None) -> tuple[str, str]:
    """Turn an existing score decision into plain task-specific advice; add no thresholds."""
    lowered = text.lower()
    if any(word in lowered for word in ('sow', 'sowing', 'seed')):
        activity = 'sowing today'
        tip = 'Tell me the crop and soil condition for more specific advice.'
        if score is None:
            return 'I cannot give a clear yes or no for sowing from the score alone.', tip
        if score >= 70:
            return 'Yes — weather-wise, you can sow today.', tip
        if score >= 45:
            return 'Maybe — sowing is possible, but there is some weather risk.', tip
        return 'No — wait before sowing; conditions look less favourable right now.', tip
    elif 'irrigat' in lowered:
        activity = 'irrigating today'
        tip = 'Check the soil moisture and the crop’s needs before choosing how much to irrigate.'
    elif any(word in lowered for word in ('drive', 'driving')):
        activity = 'driving'
        tip = 'Allow extra time and check road conditions and official warnings before leaving.'
    elif any(word in lowered for word in ('go outside', 'go out', 'outdoors', 'outdoor')):
        activity = 'going outside'
        tip = 'Choose the better weather window shown below and check official warnings before leaving.'
    else:
        activity = 'this plan'
        tip = 'Check rain and wind timing before you finalise the plan.'
    if score is None:
        return f'Weather-wise, I cannot give a clear go-ahead for {activity} from the score alone.', tip
    if score >= 70:
        return f'Yes — weather-wise, conditions look reasonably suitable for {activity}.', tip
    if score >= 45:
        return f'Maybe — {activity} is probably okay, but there is some risk.', tip
    return f'No — wait or shorten {activity}; conditions look less favourable right now.', tip


def _render_score(result: ToolResult, request: ChatRequest) -> str:
    from .chat import is_action_question

    language = chat_language(request.language)
    data = result.data if isinstance(result.data, dict) else {}
    score = data.get('score')
    label = _score_label(language, data.get('label') or 'Unavailable')
    disclaimer = phrase(language, 'score_disclaimer')
    profile = data.get('profile') or request.profile
    if score is None:
        body = phrase(language, 'score_none', label=label, disclaimer=disclaimer)
    else:
        body = phrase(language, 'score', profile=profile, score=score, label=label, disclaimer=disclaimer)
    if not is_action_question(request.text):
        return body
    lead, tip = _action_lead_and_tip(request.text, score)
    # Decision first; keep the numeric score as a short supporting line only.
    if score is None:
        support = label
    else:
        short = label.replace('conditions', '').strip() or label
        support = f'Overall it looks {short.lower()} (about {score} out of 100).'
    return f'{lead}\n\n{tip}\n\n{support}'


def _render_disaster_brief(data: dict) -> str:
    from .disaster_brief import format_disaster_brief_answer
    return format_disaster_brief_answer(data)


def _render_infrastructure_hazard(data: dict, request: ChatRequest) -> str:
    """Decision-first plain language for landslide / road connectivity estimates."""
    parts = [
        data.get('decision') or 'Infrastructure hazard estimate is available.',
        f"{data.get('place') or display_place_name(request.location.name)} · severity {data.get('severity')} ({data.get('label')})",
    ]
    inputs = data.get('inputs') or {}
    support = []
    if inputs.get('rain_24h_mm') is not None:
        support.append(f"24h rain total: {inputs['rain_24h_mm']} mm")
    if inputs.get('soil_moisture_0_to_7cm') is not None:
        support.append(f"Near-surface soil moisture: {inputs['soil_moisture_0_to_7cm']} m³/m³")
    if inputs.get('slope_percent') is not None:
        support.append(f"Local DEM slope proxy: {inputs['slope_percent']}%")
    if inputs.get('elevation_m') is not None:
        support.append(f"Elevation: {inputs['elevation_m']} m")
    if support:
        parts.append('Supporting inputs: ' + '; '.join(support) + '.')
    for factor in (data.get('factors') or [])[:4]:
        parts.append(f'• {factor}')
    infra = data.get('infrastructure') or {}
    roads = infra.get('roads_at_risk_priority') or []
    places = infra.get('settlements_nearby') or []
    if roads:
        road_names = ', '.join(str(item.get('name')) for item in roads[:6])
        parts.append(f'Nearby roads / highways that could lose connectivity: {road_names}.')
    if places:
        place_names = ', '.join(str(item.get('name')) for item in places[:6])
        parts.append(f'Nearby settlements to watch: {place_names}.')
    if infra.get('status') != 'available':
        parts.append(infra.get('message') or 'OpenStreetMap infrastructure map was unavailable for this check.')
    parts.append(data.get('disclaimer') or '')
    return '\n\n'.join(part for part in parts if part)


def render_tool_result(name: str, result: ToolResult, request: ChatRequest) -> dict:
    data = result.data
    language = chat_language(request.language)
    if name == 'get_hourly_forecast':
        answer_text = _render_hourly(result, request)
        agreement = 'hourly_forecast'
    elif name == 'get_daily_forecast':
        answer_text = _render_daily(result, request)
        agreement = 'daily_forecast'
    elif name == 'get_weather_score':
        answer_text = _render_score(result, request)
        agreement = 'weather_score'
    elif name == 'compare_locations':
        items = (data or {}).get('comparisons', []) if isinstance(data, dict) else []
        if not items:
            answer_text = phrase(language, 'compare_need_second')
        else:
            parts = [phrase(language, 'compare_intro')]
            for item in items:
                day = item.get('daily') or {}
                place = (item.get('location') or {}).get('name', 'Place')
                if day and day.get('temperature_max') is not None:
                    wind = None if day.get('wind_max_ms') is None else round(day['wind_max_ms'] * MS_TO_KMH)
                    parts.append(phrase(
                        language, 'compare_row', place=place,
                        temp=day.get('temperature_max'), rain=day.get('rain_chance_max'), wind=wind,
                    ))
                else:
                    parts.append(phrase(language, 'compare_place_unavailable', place=place))
            parts.append(phrase(language, 'compare_official'))
            answer_text = '\n'.join(parts)
        agreement = 'multi_location_compare'
    elif name == 'get_climate_summary' and isinstance(data, dict) and 'trend_per_decade' in data:
        unit = '°C per decade' if data.get('metric') == 'temperature' else 'mm per decade'
        period = data.get('period') or {}
        answer_text = phrase(
            language, 'climate', name=display_place_name(request.location.name),
            trend=f"{data['trend_per_decade']:+g}", unit=unit,
            start=period.get('start_year'), end=period.get('end_year'),
            coverage=f"{data.get('coverage', 0)*100:.1f}",
        )
        agreement = 'single_reanalysis_source'
    elif name == 'get_active_alerts':
        alerts = data or []
        if alerts:
            answer_text = '\n\n'.join(format_official_warning(language, alert) for alert in alerts)
        elif result.status == 'available':
            answer_text = phrase(language, 'alerts_none')
        else:
            answer_text = result.error or phrase(language, 'alerts_unknown')
        agreement = 'official_alerts'
    elif name == 'get_provider_status' and isinstance(data, dict):
        names = [item.get('provider') for item in data.get('providers', []) if item.get('status') == 'available']
        answer_text = phrase(language, 'providers', names=', '.join(str(item) for item in names if item) or 'none')
        agreement = 'providers'
    elif name == 'get_saved_locations':
        places = (data or {}).get('locations') or []
        names = ', '.join(item.get('name', 'Place') for item in places)
        answer_text = phrase(language, 'saved_places', names=names) if places else phrase(language, 'saved_none')
        agreement = 'saved_locations'
    elif name == 'set_alert_rule' and isinstance(data, dict):
        answer_text = phrase(
            language, 'alert_rule',
            place=data.get('location', 'this place'),
            channels=', '.join(data.get('channels') or []),
        )
        agreement = 'alert_rule'
    elif name == 'get_agromet_advisory':
        answer_text = phrase(language, 'agromet')
        agreement = 'agromet'
    elif name == 'assess_infrastructure_hazard' and isinstance(data, dict):
        answer_text = _render_infrastructure_hazard(data, request)
        agreement = 'infrastructure_hazard_estimate'
    elif name == 'get_disaster_briefing' and isinstance(data, dict):
        answer_text = _render_disaster_brief(data)
        agreement = 'disaster_briefing'
    else:
        answer_text = result.error or phrase(language, 'unavailable')
        agreement = 'tool'
    return _attach_tool({
        'answer': answer_text,
        'language': language,
        'day_offset': request.day_offset,
        'retrieved_at': result.retrieved_at,
        'is_stale': result.is_stale,
        'sources': result.sources,
        'agreement': agreement,
        'conversation_context': context(request, result.retrieved_at, name),
    }, name)


def _humanize_payload(payload: dict) -> dict:
    from .layperson import format_layperson_answer
    answer = payload.get('answer')
    if isinstance(answer, str) and answer.strip():
        payload = {**payload, 'answer': format_layperson_answer(answer)}
    return payload


async def run_chat(request: ChatRequest) -> dict:
    started = time.perf_counter()
    # Prefer Groq tool orchestration when available; deterministic path is always the safety net.
    try:
        from .groq_orchestrator import orchestrate_chat
        orchestrated = await orchestrate_chat(request)
        if orchestrated is not None:
            _trace(
                orchestrated.get('tool') or 'orchestrated',
                orchestrated.get('tool') or 'orchestrated',
                int((time.perf_counter() - started) * 1000),
                'available',
            )
            return _humanize_payload(orchestrated)
        _LOG.info('FALLBACK_USED reason=orchestrator_none path=deterministic')
    except Exception as error:
        _LOG.info('FALLBACK_USED reason=orchestrator_exception exception=%s', type(error).__name__)

    intent, name = await resolve_tool(request)
    status = 'error'
    try:
        if name == 'get_current_weather':
            payload = await _forecast_answer(request, name)
            status = 'available'
            payload['response_origin'] = 'deterministic_fallback'
            return _humanize_payload(payload)
        try:
            result = await invoke_registered_tool(name, request)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            status = 'unavailable'
            payload = await _forecast_answer(request, 'get_current_weather')
            payload['response_origin'] = 'deterministic_fallback'
            return _humanize_payload(payload)
        status = result.status
        if name == 'get_marine_forecast':
            if result.status == 'unavailable':
                payload = await _forecast_answer(request, name)
                payload['response_origin'] = 'deterministic_fallback'
                return _humanize_payload(payload)
            payload = await _marine_answer(request, result)
            payload['response_origin'] = 'deterministic_fallback'
            return _humanize_payload(payload)
        if name == 'get_climate_summary' and (
            result.status == 'unavailable' or not isinstance(result.data, dict) or 'trend_per_decade' not in (result.data or {})
        ):
            payload = await _forecast_answer(request, name)
            payload['response_origin'] = 'deterministic_fallback'
            return _humanize_payload(payload)
        if name in {'get_hourly_forecast', 'get_daily_forecast', 'get_weather_score'} and result.status == 'unavailable':
            payload = await _forecast_answer(request, name)
            payload['response_origin'] = 'deterministic_fallback'
            return _humanize_payload(payload)
        # Event / heavy-rain / why answers need fusion disagreement + alerts, not hourly-only drafts.
        if name == 'get_hourly_forecast':
            from .event_risk import is_event_question, is_heavy_rain_or_flood_question, is_why_question
            if (
                is_event_question(request.text)
                or is_heavy_rain_or_flood_question(request.text)
                or is_why_question(request.text)
            ):
                payload = await _forecast_answer(request, name)
                payload['response_origin'] = 'deterministic_fallback'
                return _humanize_payload(payload)
        payload = render_tool_result(name, result, request)
        if name == 'get_weather_score' and result.status == 'available':
            data, official = await asyncio.gather(
                service.bundle(request.location),
                alert_service.official(request.location),
            )
            data = {
                **data,
                'official_status': official['status'],
                'alerts_status': official['status'],
                'official_alerts': official['alerts'],
                'alerts': official['alerts'],
            }
            extra = grounded_advice_lines(request, data)
            if extra:
                # Keep at most one short tip — layperson formatter drops disagreement dumps.
                tip = next((line for line in extra if 'models differ' not in line.lower() and 'sources disagree' not in line.lower()), None)
                if tip:
                    payload['answer'] = payload['answer'] + '\n\n' + tip
        payload['response_origin'] = 'deterministic_fallback'
        return _humanize_payload(payload)
    finally:
        _trace(intent, name, int((time.perf_counter() - started) * 1000), status)
