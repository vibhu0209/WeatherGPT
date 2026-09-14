"""Timed outdoor-event risk and short grounded 'why' lines.

Uses verified hourly forecast fields only — never radar, never invented flood certainty.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import MS_TO_KMH


EVENT_WORDS = (
    'event', 'outdoor event', 'wedding', 'match', 'function', 'party', 'gathering',
    'ceremony', 'picnic', 'programme', 'program', 'meeting outside',
)
HEAVY_RAIN_WORDS = (
    'flood', 'flooding', 'waterlog', 'waterlogging', 'heavy rain', 'heavy rainfall',
    'downpour', 'cloudburst', 'flash flood', 'inundat', 'बाढ़', 'जलभराव', 'मूसलाधार',
)
WHY_WORDS = (
    'why is', 'why are', 'why this', 'why the', 'what causes', 'reason for',
    'why raining', 'why rain', 'explain why', 'क्यों', 'क्या वजह',
)


def is_event_question(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in EVENT_WORDS) or bool(parse_clock_point(text))


def is_heavy_rain_or_flood_question(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in HEAVY_RAIN_WORDS)


def is_why_question(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in WHY_WORDS)


def parse_clock_point(text: str, timezone_name: str = 'Asia/Kolkata', now: datetime | None = None):
    """Parse 'at 4 PM', '4pm', '16:00' into a local hour start (aware) or None."""
    zone = ZoneInfo(timezone_name)
    local_now = (now or datetime.now(zone)).astimezone(zone)
    patterns = (
        r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b',
        r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b',
        r'\b(\d{1,2})\s*o\'?clock\b',
        r'\b([01]?\d|2[0-3]):([0-5]\d)\b',
    )
    match = None
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            break
    if not match:
        return None

    hour = int(match.group(1)) % 24
    minute = int(match.group(2) or 0) if match.lastindex and match.lastindex >= 2 and match.group(2) else 0
    period = ''
    if match.lastindex and match.lastindex >= 3 and match.group(3):
        period = match.group(3).lower()
    # 24h times from HH:MM pattern have no am/pm.
    if period == 'pm' and hour < 12:
        hour += 12
    elif period == 'am' and hour == 12:
        hour = 0
    elif not period and match.re.pattern.endswith(r"o\'?clock\b") and 1 <= hour <= 7:
        # Bare "4 o'clock" in afternoon-event context → prefer 16:00.
        hour += 12

    point = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if point < local_now - timedelta(hours=1):
        point = point + timedelta(days=1)
    return point


def parse_clock_window(text: str, timezone_name: str, now: datetime | None = None):
    """±1 hour around a named clock time for event questions."""
    point = parse_clock_point(text, timezone_name, now)
    if point is None:
        return None, None
    start = point - timedelta(hours=1)
    end = point + timedelta(hours=2)
    return start, end


def _max_field(rows: list[dict], field: str) -> float | None:
    values = [row.get(field) for row in rows if row.get(field) is not None]
    if not values:
        return None
    return float(max(values))


def _sum_field(rows: list[dict], field: str) -> float | None:
    values = [row.get(field) for row in rows if row.get(field) is not None]
    if not values:
        return None
    return round(sum(float(v) for v in values), 1)


def assess_timed_event_risk(rows: list[dict], *, place: str, window_label: str) -> dict:
    """Decision-first outdoor / heavy-rain risk for a clock window. Not a flood forecast."""
    rain_chance = _max_field(rows, 'rain_chance')
    rain_mm = _sum_field(rows, 'rain_mm')
    wind_ms = _max_field(rows, 'wind_ms')
    temp = _max_field(rows, 'temperature')

    score = 0
    factors: list[str] = []
    if rain_chance is not None:
        if rain_chance >= 70:
            score += 40
            factors.append(f'Rain chance peaks around {rain_chance:g}% in this window')
        elif rain_chance >= 45:
            score += 25
            factors.append(f'Rain chance peaks around {rain_chance:g}% in this window')
        elif rain_chance >= 25:
            score += 12
            factors.append(f'Some rain chance (about {rain_chance:g}%) in this window')
    if rain_mm is not None:
        if rain_mm >= 20:
            score += 35
            factors.append(f'Heavy forecast rainfall total (~{rain_mm:g} mm) in this window')
        elif rain_mm >= 8:
            score += 20
            factors.append(f'Moderate forecast rainfall total (~{rain_mm:g} mm) in this window')
        elif rain_mm >= 2:
            score += 8
            factors.append(f'Light forecast rainfall total (~{rain_mm:g} mm) in this window')
    if wind_ms is not None and wind_ms * MS_TO_KMH >= 40:
        score += 15
        factors.append(f'Strong wind (about {wind_ms * MS_TO_KMH:.0f} km/h)')
    if temp is not None and temp >= 38:
        score += 10
        factors.append(f'High heat (about {temp:g}°C)')

    if score >= 55:
        severity = 'high'
        decision = (
            f'High disruption risk for an outdoor plan around {window_label} in {place} — '
            f'heavy rain / waterlogging disruption is plausible from the forecast. Prefer indoor backup.'
        )
    elif score >= 30:
        severity = 'elevated'
        decision = (
            f'Elevated risk around {window_label} in {place} — rain may disturb an outdoor event. '
            f'Keep a covered backup and flexible timing.'
        )
    elif score >= 12:
        severity = 'watch'
        decision = (
            f'Watch around {window_label} in {place} — some rain or weather inconvenience is possible. '
            f'The plan can go ahead with a flexible backup.'
        )
    else:
        severity = 'lower'
        decision = (
            f'Lower outdoor disruption risk around {window_label} in {place} from the available forecast — '
            f'still not a guarantee; check official warnings closer to the time.'
        )

    flood_note = (
        'This is a WeatherGPT forecast-based outdoor disruption estimate — not a flood model, '
        'not live radar, and not an official municipal inundation warning.'
    )
    return {
        'decision': decision,
        'severity': severity,
        'score': score,
        'factors': factors,
        'inputs': {
            'rain_chance_max': rain_chance,
            'rain_mm_total': rain_mm,
            'wind_ms_max': wind_ms,
            'temperature_max': temp,
            'window_label': window_label,
        },
        'disclaimer': flood_note,
    }


def format_event_risk_answer(
    assessment: dict,
    *,
    why_line: str | None = None,
    user_text: str | None = None,
) -> str:
    parts = [assessment['decision']]
    for factor in (assessment.get('factors') or [])[:3]:
        parts.append(f'• {factor}')
    if why_line:
        parts.append(why_line)
    lowered = (user_text or '').lower()
    if 'radar' in lowered or 'डॉपलर' in lowered or 'राडार' in lowered:
        parts.append(
            'Live weather radar is not available in WeatherGPT yet — this answer uses verified hourly forecasts only.'
        )
    parts.append(assessment.get('disclaimer') or '')
    return '\n\n'.join(part for part in parts if part)


def why_weather_brief(bundle: dict) -> str | None:
    """One short grounded why-line from fusion metadata / alerts — never invent synoptic stories."""
    official = bundle.get('official_alerts') or bundle.get('alerts') or []
    if official:
        headline = official[0].get('headline') or official[0].get('event') or 'an official warning'
        return f'Why it matters now: an official warning is active ({headline}). Follow that first.'

    reasons = [str(item).strip() for item in (bundle.get('disagreement_reasons') or []) if str(item).strip()]
    agreement = (bundle.get('agreement') or '').lower()
    sources = [str(item) for item in (bundle.get('sources') or []) if item]
    source_count = bundle.get('source_count') or len(sources)

    if reasons:
        return f'Why the outlook is uncertain: {reasons[0]}'
    if agreement == 'sources_disagree' and source_count:
        return (
            f'Why guidance stays cautious: {source_count} weather sources do not fully agree on timing or intensity.'
        )
    if agreement == 'multi_source_consensus' and source_count >= 2:
        names = ', '.join(sources[:3])
        return f'Why this reading is steadier: {source_count} sources broadly agree ({names}).'
    if sources:
        return f'Why we say this: based on verified forecast sources ({", ".join(sources[:3])}).'
    return None


def clock_window_label(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%I:%M %p').lstrip('0')}–{end.strftime('%I:%M %p').lstrip('0')}"
