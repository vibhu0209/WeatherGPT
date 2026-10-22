"""Contiguous spray/harvest work-window planner.

Eligibility reuses the exact thresholds in ``decision.spray_window`` and
``decision.harvest_window`` without changing those functions:

- Spray: rain_chance <= 20 and wind_ms <= 5 (both fields required).
- Harvest: rain_chance <= 30, wind_ms is None or <= 8, weather_code not in
  THUNDER_CODES {95, 96, 99}. rain_chance is required.

Duration is the count of consecutive qualifying hourly points. The exclusive
end is the last qualifying timestamp plus one hour.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from .decision import THUNDER_CODES

SUPPORTED_ACTIVITIES = ('spray', 'harvest')
DEFAULT_MIN_HOURS = 2
MAX_HOURLY_POINTS = 48
AVOID_RAIN_THRESHOLD = 60
DISCLAIMER = (
    'This is general weather-based guidance, not crop-specific agricultural advice. '
    'The best window is not a guarantee of safety or suitability.'
)


class UnsupportedActivityError(ValueError):
    """Raised when activity is not spray or harvest."""


def _zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except Exception as error:
        raise ValueError('Unknown timezone') from error


def _parse_time(point: dict) -> datetime | None:
    raw = point.get('time') if isinstance(point, dict) else None
    if raw is None:
        return None
    try:
        stamp = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    if not isinstance(stamp, datetime):
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(timezone.utc)


def spray_hour_eligible(point: dict) -> bool | None:
    """True/False if spray rules can be evaluated; None if a required field is missing."""
    rain = point.get('rain_chance')
    wind = point.get('wind_ms')
    if rain is None or wind is None:
        return None
    return rain <= 20 and wind <= 5


def harvest_hour_eligible(point: dict) -> bool | None:
    """True/False if harvest rules can be evaluated; None if rain_chance is missing."""
    rain = point.get('rain_chance')
    if rain is None:
        return None
    wind = point.get('wind_ms')
    if rain > 30:
        return False
    if wind is not None and wind > 8:
        return False
    if point.get('weather_code') in THUNDER_CODES:
        return False
    return True


def _eligible(point: dict, activity: str) -> bool | None:
    if activity == 'spray':
        return spray_hour_eligible(point)
    return harvest_hour_eligible(point)


def _avoid_state(point: dict) -> tuple[bool | None, str | None]:
    """Return (is_avoid, reason). None means the avoid condition cannot be evaluated."""
    rain = point.get('rain_chance')
    code = point.get('weather_code')
    thunder = code in THUNDER_CODES if code is not None else None
    high_rain = rain is not None and rain >= AVOID_RAIN_THRESHOLD
    # A confirmed high-rain or thunderstorm observation is enough to avoid the
    # hour. Otherwise both inputs are needed before it can be called safe.
    if not high_rain and thunder is None:
        return None, None
    if rain is None and thunder is not True:
        return None, None
    if not high_rain and not thunder:
        return False, None
    if high_rain and thunder:
        reason = 'high rain probability and thunderstorm conditions'
    elif thunder:
        reason = 'thunderstorm conditions'
    else:
        reason = 'high rain probability'
    return True, reason


def _consecutive(previous: datetime, current: datetime) -> bool:
    return current - previous == timedelta(hours=1)


def _window_payload(start: datetime, last: datetime, zone: ZoneInfo, extra: dict | None = None) -> dict:
    duration = int((last - start) / timedelta(hours=1)) + 1
    end = last + timedelta(hours=1)
    payload = {
        'start_local': start.astimezone(zone).isoformat(),
        'end_local': end.astimezone(zone).isoformat(),
        'duration_hours': duration,
    }
    if extra:
        payload.update(extra)
    return payload


def _normalize_hourly(hourly: list[dict], now: datetime) -> list[tuple[datetime | None, dict | None]]:
    """Normalize valid rows while retaining malformed-time boundaries.

    Providers normally return sorted, complete timestamps.  When a caller
    supplies an absent, invalid, or duplicate timestamp, that observation is
    not silently discarded: it becomes a boundary so a work or avoid window
    can never bridge unknown forecast data.
    """
    current_hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    groups: list[list[tuple[datetime, dict]]] = []
    current_group: list[tuple[datetime, dict]] = []
    seen: set[datetime] = set()
    for point in hourly or []:
        stamp = _parse_time(point)
        if stamp is None:
            if current_group:
                groups.append(current_group)
                current_group = []
            groups.append([])
            continue
        stamp = stamp.replace(minute=0, second=0, microsecond=0)
        if stamp in seen:
            if current_group:
                groups.append(current_group)
                current_group = []
            groups.append([])
            continue
        seen.add(stamp)
        current_group.append((stamp, point))
    if current_group:
        groups.append(current_group)

    normalized: list[tuple[datetime | None, dict | None]] = []
    valid_count = 0
    for group in groups:
        if not group:
            normalized.append((None, None))
            continue
        for stamp, point in sorted(group, key=lambda item: item[0]):
            if stamp < current_hour:
                continue
            if valid_count >= MAX_HOURLY_POINTS:
                break
            normalized.append((stamp, point))
            valid_count += 1
        if valid_count >= MAX_HOURLY_POINTS:
            break
    return normalized


def _collect_runs(
    rows: list[tuple[datetime | None, dict | None]],
    qualifies,
) -> list[tuple[datetime, datetime, list]]:
    runs: list[tuple[datetime, datetime, list]] = []
    run_start: datetime | None = None
    run_last: datetime | None = None
    run_meta: list = []

    def close():
        nonlocal run_start, run_last, run_meta
        if run_start is not None and run_last is not None:
            runs.append((run_start, run_last, run_meta))
        run_start = None
        run_last = None
        run_meta = []

    for stamp, point in rows:
        if stamp is None or point is None:
            close()
            continue
        state = qualifies(point)
        if state is None:
            close()
            continue
        if not state:
            close()
            continue
        if run_last is None:
            run_start, run_last, run_meta = stamp, stamp, [point]
            continue
        if _consecutive(run_last, stamp):
            run_last = stamp
            run_meta.append(point)
        else:
            close()
            run_start, run_last, run_meta = stamp, stamp, [point]
    close()
    return runs


def plan_work_windows(
    hourly: list[dict],
    activity: str,
    timezone_name: str,
    min_hours: int = DEFAULT_MIN_HOURS,
    *,
    now: datetime | None = None,
    is_stale: bool = False,
    sources: list | None = None,
    official_alerts: list | None = None,
    official_status: str | None = None,
    official_message: str | None = None,
) -> dict[str, Any]:
    if activity not in SUPPORTED_ACTIVITIES:
        raise UnsupportedActivityError('Unsupported activity. Use spray or harvest.')
    if min_hours < 1:
        raise ValueError('min_hours must be at least 1')
    zone = _zone(timezone_name)
    reference = now or datetime.now(timezone.utc)
    rows = _normalize_hourly(hourly, reference)

    empty = {
        'activity': activity,
        'status': 'unavailable',
        'message': 'No usable hourly forecast is available, so a reliable work window cannot be determined.',
        'work_windows': [],
        'best_window': None,
        'avoid_windows': [],
        'is_stale': bool(is_stale),
        'sources': list(sources or []),
        'official_status': official_status,
        'official_alerts': list(official_alerts or []),
        'official_message': official_message,
        'official_warnings_take_precedence': True,
        'disclaimer': DISCLAIMER,
        'min_hours': min_hours,
    }
    if not rows:
        return empty

    qualifying = _collect_runs(rows, lambda point: _eligible(point, activity))
    work_windows = [
        _window_payload(start, last, zone)
        for start, last, _meta in qualifying
        if int((last - start) / timedelta(hours=1)) + 1 >= min_hours
    ]
    work_windows.sort(key=lambda item: item['start_local'])
    best = None
    if work_windows:
        longest = max(item['duration_hours'] for item in work_windows)
        best = min(
            (item for item in work_windows if item['duration_hours'] == longest),
            key=lambda item: item['start_local'],
        )

    avoid_runs = _collect_runs(rows, lambda point: _avoid_state(point)[0] is True)
    avoid_windows = []
    for start, last, meta in avoid_runs:
        reasons = []
        for point in meta:
            _is_avoid, reason = _avoid_state(point)
            if reason and reason not in reasons:
                reasons.append(reason)
        if 'high rain probability and thunderstorm conditions' in reasons:
            reason = 'high rain probability and thunderstorm conditions'
        elif len(reasons) > 1:
            reason = 'high rain probability and thunderstorm conditions'
        else:
            reason = reasons[0] if reasons else 'high rain probability'
        avoid_windows.append(_window_payload(start, last, zone, {'reason': reason}))

    if work_windows:
        message = (
            f'Found {len(work_windows)} qualifying {activity} window(s) of at least {min_hours} consecutive hours.'
        )
    else:
        message = (
            f'Usable hourly forecast data is available, but no contiguous {activity} window of at least '
            f'{min_hours} hours meets the existing eligibility rules.'
        )

    return {
        'activity': activity,
        'status': 'available',
        'message': message,
        'work_windows': work_windows,
        'best_window': best,
        'avoid_windows': avoid_windows,
        'is_stale': bool(is_stale),
        'sources': list(sources or []),
        'official_status': official_status,
        'official_alerts': list(official_alerts or []),
        'official_message': official_message,
        'official_warnings_take_precedence': True,
        'disclaimer': DISCLAIMER,
        'min_hours': min_hours,
    }


def infer_work_activity(text: str) -> Literal['spray', 'harvest'] | None:
    lowered = text.lower()
    harvest_words = ('harvest', 'harvesting', 'कटाई', 'కోత', 'அறுவடை', 'कापणी')
    spray_words = ('spray', 'spraying', 'छिड़काव', 'स्प्रे', 'স্প্রে', 'స్ప్రే')
    harvest = any(word in lowered for word in harvest_words)
    spray = any(word in lowered for word in spray_words)
    if harvest and not spray:
        return 'harvest'
    if spray and not harvest:
        return 'spray'
    if spray and harvest:
        return 'spray' if lowered.find('spray') <= lowered.find('harvest') else 'harvest'
    return None


def _clock(iso_stamp: str) -> str:
    stamp = datetime.fromisoformat(iso_stamp)
    return stamp.strftime('%H:%M')


def format_work_window_answer(plan: dict, activity: str | None = None) -> str:
    chosen = activity or plan.get('activity') or 'spray'
    parts: list[str] = []
    if plan.get('is_stale'):
        parts.append('Showing weather saved earlier. Treat this window as possibly out of date.')
    best = plan.get('best_window')
    if plan.get('status') == 'unavailable':
        parts.append(plan.get('message') or 'A reliable work window cannot be determined from the available forecast.')
    elif best:
        start = _clock(best['start_local'])
        end = _clock(best['end_local'])
        hours = best['duration_hours']
        parts.append(f'Your best {chosen} window is {start}–{end} local time ({hours} hours).')
    else:
        parts.append('No suitable contiguous window was found in the available forecast.')
    avoid = plan.get('avoid_windows') or []
    if avoid:
        first = avoid[0]
        reason = first.get('reason') or 'unfavourable weather'
        if 'thunder' in reason and 'rain' in reason:
            spoken = 'rain probability is high and thunderstorm conditions are indicated'
        elif 'thunder' in reason:
            spoken = 'thunderstorm conditions are indicated'
        else:
            spoken = 'rain probability is high'
        parts.append(
            f"Avoid {_clock(first['start_local'])}–{_clock(first['end_local'])} because {spoken}."
        )
    alerts = [alert for alert in (plan.get('official_alerts') or []) if alert]
    status = plan.get('official_status')
    if alerts:
        top = alerts[0]
        headline = (top.get('headline') or top.get('event') or 'Official weather warning').strip()
        parts.append(
            f'Official warning: {headline}. Official warnings take precedence over planner suggestions.'
        )
    elif status and status != 'available':
        parts.append(
            'Official alert status could not be verified. That does not mean there are no warnings.'
        )
    elif status == 'available':
        parts.append('No active official weather warning is listed for this place.')
    parts.append(plan.get('disclaimer') or DISCLAIMER)
    return '\n\n'.join(parts)


def plan_from_bundle(
    bundle: dict,
    activity: str,
    timezone_name: str,
    min_hours: int = DEFAULT_MIN_HOURS,
    *,
    now: datetime | None = None,
    official_alerts: list | None = None,
    official_status: str | None = None,
    official_message: str | None = None,
) -> dict[str, Any]:
    alerts = official_alerts
    if alerts is None:
        alerts = bundle.get('official_alerts') or bundle.get('alerts') or []
    status = official_status
    if status is None:
        status = bundle.get('official_status') or bundle.get('alerts_status')
    message = official_message if official_message is not None else bundle.get('alerts_message')
    return plan_work_windows(
        bundle.get('hourly') or [],
        activity,
        timezone_name,
        min_hours,
        now=now,
        is_stale=bool(bundle.get('is_stale')),
        sources=bundle.get('sources'),
        official_alerts=alerts,
        official_status=status,
        official_message=message,
    )
