from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .models import MS_TO_KMH

ALL_PROFILES = (
    'general', 'farming', 'fishing', 'outdoor', 'tourism', 'transport',
    'construction', 'emergency', 'vendor', 'aviation', 'research',
)

PROFILE_CONFIG = {
    'general': {'rain_mult': 0.30, 'wind_thresh': 8, 'heat_thresh': 37, 'vis_thresh': 2000, 'uv_sensitive': False},
    'farming': {'rain_mult': 0.45, 'wind_thresh': 5, 'heat_thresh': 34, 'vis_thresh': 1500, 'uv_sensitive': False},
    'fishing': {'rain_mult': 0.35, 'wind_thresh': 8, 'heat_thresh': 38, 'vis_thresh': 2000, 'uv_sensitive': False,
                'wave_thresh_m': 1.5, 'swell_thresh_m': 2.0},
    'outdoor': {'rain_mult': 0.40, 'wind_thresh': 7, 'heat_thresh': 34, 'vis_thresh': 1500, 'uv_sensitive': False},
    'tourism': {'rain_mult': 0.35, 'wind_thresh': 10, 'heat_thresh': 35, 'vis_thresh': 3000, 'uv_sensitive': True},
    'transport': {'rain_mult': 0.50, 'wind_thresh': 9, 'heat_thresh': 38, 'vis_thresh': 2000, 'uv_sensitive': False},
    'construction': {'rain_mult': 0.50, 'wind_thresh': 6, 'heat_thresh': 34, 'vis_thresh': 1500, 'uv_sensitive': False},
    'emergency': {'rain_mult': 0.55, 'wind_thresh': 10, 'heat_thresh': 38, 'vis_thresh': 1000, 'uv_sensitive': False},
    'vendor': {'rain_mult': 0.45, 'wind_thresh': 8, 'heat_thresh': 36, 'vis_thresh': 1500, 'uv_sensitive': False},
    'aviation': {'rain_mult': 0.35, 'wind_thresh': 12, 'heat_thresh': 40, 'vis_thresh': 5000, 'uv_sensitive': False},
    'research': {'rain_mult': 0.25, 'wind_thresh': 10, 'heat_thresh': 38, 'vis_thresh': 2000, 'uv_sensitive': False},
}


def daily_summary(hourly: list[dict], timezone_name: str) -> list[dict]:
    zone = ZoneInfo(timezone_name)
    days: dict[str, list[dict]] = defaultdict(list)
    for point in hourly:
        local = datetime.fromisoformat(point["time"]).astimezone(zone)
        days[local.date().isoformat()].append(point)

    result = []
    for day, points in sorted(days.items()):
        def values(name: str):
            return [p[name] for p in points if p.get(name) is not None]

        temperatures = values("temperature")
        rain_chances = values("rain_chance")
        rain_amounts = values("rain_mm")
        winds = values("wind_ms")
        humidities = values("humidity")
        result.append({
            "date": day,
            "temperature_min": min(temperatures) if temperatures else None,
            "temperature_max": max(temperatures) if temperatures else None,
            "rain_chance_max": max(rain_chances) if rain_chances else None,
            "rain_total_mm": round(sum(rain_amounts), 1) if rain_amounts else None,
            "wind_max_ms": max(winds) if winds else None,
            "humidity_average": round(sum(humidities) / len(humidities), 1) if humidities else None,
            "source_count": max((p.get("source_count", 0) for p in points), default=0),
        })
    return result


def current_point(hourly: list[dict]) -> dict | None:
    if not hourly:
        return None
    now = datetime.now(timezone.utc)
    return min(hourly, key=lambda p: abs((datetime.fromisoformat(p["time"]) - now).total_seconds()))


def spray_window(hourly: list[dict], timezone_name: str = 'Asia/Kolkata') -> dict:
    """Deterministic dry/low-wind window for crop spraying questions. Not crop-specific advice."""
    zone = ZoneInfo(timezone_name)
    windows = []
    for point in hourly[:24]:
        rain = point.get('rain_chance')
        wind = point.get('wind_ms')
        if rain is None or wind is None:
            continue
        if rain <= 20 and wind <= 5:
            local = datetime.fromisoformat(point['time']).astimezone(zone)
            windows.append(local.strftime('%H:%M'))
    return {
        'suitable_hours_local': windows[:6],
        'status': 'available' if windows else 'unavailable',
        'message': (
            f"Lower rain and wind appear around {', '.join(windows[:3])} local time based on the forecast."
            if windows else
            "No low-rain and low-wind spray window was found in the next 24 hours of the forecast."
        ),
        'disclaimer': 'Check your local agricultural advisory before spraying. This is not crop-specific advice.',
    }


THUNDER_CODES = {95, 96, 99}
PERIODS = (('morning', 6, 12), ('afternoon', 12, 17), ('evening', 17, 22))
COASTAL_WARNING_MARKERS = (
    'cyclone', 'storm surge', 'fishermen', 'fisherman', 'coastal', 'tsunami',
    'high wave', 'high seas', 'squall',
)
RAIN_MENTION = 40
RAIN_RISE_DELTA = 15


def harvest_window(hourly: list[dict], timezone_name: str = 'Asia/Kolkata') -> dict:
    """Drier, lower-wind hours for field work. Not crop-specific harvest advice."""
    zone = _zone(timezone_name)
    windows = []
    for point in hourly[:24]:
        rain = point.get('rain_chance')
        wind = point.get('wind_ms')
        if rain is None:
            continue
        if rain <= 30 and (wind is None or wind <= 8) and point.get('weather_code') not in THUNDER_CODES:
            windows.append(_local(point, zone).strftime('%H:%M'))
    hours = ', '.join(windows[:4])
    return {
        'suitable_hours_local': windows[:8],
        'status': 'available' if windows else 'unavailable',
        'message': (
            f"Drier hours for field work look like {hours} local time, based on rain at or below 30% and no thunderstorm codes."
            if windows else
            "No drier harvest-style window was found in the next 24 hours of the forecast."
        ),
        'disclaimer': 'This is not crop-specific harvest advice. Check your local agricultural advisory.',
    }


def _zone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name or 'Asia/Kolkata')
    except Exception:
        return ZoneInfo('Asia/Kolkata')


def _local(point: dict, zone):
    return datetime.fromisoformat(point['time']).astimezone(zone)


def _rec(
    severity: str,
    message: str,
    *,
    variable: str,
    time_window: str,
    rule: str,
    source: str,
    key: str | None = None,
    params: dict | None = None,
    value=None,
) -> dict:
    item = {
        'severity': severity,
        'message': message,
        'variable': variable,
        'time_window': time_window,
        'rule': rule,
        'source': source,
    }
    if key:
        item['key'] = key
    if params:
        item['params'] = params
    if value is not None:
        item['value'] = value
    return item


def _extreme(hourly: list[dict], field: str, zone, *, pick=max, limit: int = 24):
    rows = [point for point in hourly[:limit] if point.get(field) is not None]
    if not rows:
        return None, None, None
    chosen = pick(rows, key=lambda point: point[field])
    return chosen, chosen[field], _local(chosen, zone).strftime('%H:%M')


def _period_stats(hourly: list[dict], zone) -> list[dict]:
    stats = []
    for name, start_hour, end_hour in PERIODS:
        rows = [point for point in hourly[:24] if start_hour <= _local(point, zone).hour < end_hour]
        if not rows:
            continue
        _, rain, rain_hour = _extreme(rows, 'rain_chance', zone, limit=len(rows))
        _, wind, wind_hour = _extreme(rows, 'wind_ms', zone, limit=len(rows))
        _, heat, heat_hour = _extreme(rows, 'temperature', zone, limit=len(rows))
        _, gust, gust_hour = _extreme(rows, 'wind_gust_ms', zone, limit=len(rows))
        _, uv, uv_hour = _extreme(rows, 'uv_index', zone, limit=len(rows))
        _, visibility, vis_hour = _extreme(rows, 'visibility_m', zone, pick=min, limit=len(rows))
        thunder_rows = [point for point in rows if point.get('weather_code') in THUNDER_CODES]
        stats.append({
            'name': name,
            'start_hour': start_hour,
            'end_hour': end_hour,
            'window': f'{start_hour:02d}:00–{end_hour:02d}:00 local',
            'rain': rain,
            'rain_hour': rain_hour,
            'wind': wind,
            'wind_hour': wind_hour,
            'heat': heat,
            'heat_hour': heat_hour,
            'gust': gust,
            'gust_hour': gust_hour,
            'uv': uv,
            'uv_hour': uv_hour,
            'visibility': visibility,
            'vis_hour': vis_hour,
            'thunder': bool(thunder_rows),
            'thunder_hour': _local(thunder_rows[0], zone).strftime('%H:%M') if thunder_rows else None,
        })
    return stats


def _period_penalty(stat: dict, config: dict) -> float:
    rain = stat.get('rain') or 0
    wind = stat.get('wind') or 0
    heat = stat.get('heat') or 0
    return (
        rain * config['rain_mult']
        + max(0, wind - config['wind_thresh']) * 4
        + max(0, heat - config['heat_thresh']) * 2
        + (25 if stat.get('thunder') else 0)
    )


def _first_rain_rise(hourly: list[dict], zone, after_hour: int, threshold: float):
    for point in hourly[:24]:
        rain = point.get('rain_chance')
        if rain is None:
            continue
        local = _local(point, zone)
        if local.hour + local.minute / 60 >= after_hour and rain >= threshold:
            return local.strftime('%H:%M'), rain
    return None, None


def _forecast_source(sources: list | None, fallback: str = 'hourly_forecast') -> str:
    names = [str(item) for item in (sources or []) if item]
    return ','.join(names[:3]) if names else fallback


def _alert_text(alert: dict) -> str:
    return ' '.join(str(alert.get(key) or '') for key in ('headline', 'event', 'instruction', 'description')).lower()


def weather_score(hourly: list[dict], profile: str, marine_hourly: list[dict] | None = None) -> dict:
    if profile == 'fishing' and not marine_hourly:
        return {
            'score': None, 'label': 'Marine safety score unavailable', 'profile': profile,
            'components': [], 'limiting_factors': ['Wave, sea-state and official fishermen warning inputs are required'],
            'disclaimer': 'Land weather cannot certify that fishing is safe. Check official IMD and INCOIS warnings.',
        }
    future = hourly[:24]
    if not future and profile != 'fishing':
        return {
            "score": None,
            "label": "Unavailable",
            "profile": profile,
            "components": [],
            "limiting_factors": ["Forecast data is unavailable"],
            "disclaimer": "This score is not an official safety certification.",
        }

    config = PROFILE_CONFIG.get(profile, PROFILE_CONFIG['general'])
    rain = max((p["rain_chance"] for p in future if p.get("rain_chance") is not None), default=None) if future else None
    wind = max((p["wind_ms"] for p in future if p.get("wind_ms") is not None), default=None) if future else None
    heat = max((p["temperature"] for p in future if p.get("temperature") is not None), default=None) if future else None
    visibility = min((p["visibility_m"] for p in future if p.get("visibility_m") is not None), default=None) if future else None
    uv = max((p["uv_index"] for p in future if p.get("uv_index") is not None), default=None) if future else None
    thunder = any(p.get("weather_code") in {95, 96, 99} for p in future) if future else False
    penalties: list[tuple[str, int, str]] = []

    if profile == 'fishing' and marine_hourly:
        waves = [p['wave_height_m'] for p in marine_hourly[:24] if p.get('wave_height_m') is not None]
        swells = [p['swell_height_m'] for p in marine_hourly[:24] if p.get('swell_height_m') is not None]
        if waves:
            peak = max(waves)
            penalty = min(45, round(max(0, peak - config['wave_thresh_m']) * 20))
            penalties.append(("Waves", penalty, f"Highest significant wave height is {peak:g} m"))
        if swells:
            peak = max(swells)
            penalty = min(30, round(max(0, peak - config['swell_thresh_m']) * 12))
            penalties.append(("Swell", penalty, f"Highest swell height is {peak:g} m"))
        if not waves and not swells:
            return {
                'score': None, 'label': 'Marine safety score unavailable', 'profile': profile,
                'components': [], 'limiting_factors': ['Marine wave fields were empty'],
                'disclaimer': 'Land weather cannot certify that fishing is safe. Check official IMD and INCOIS warnings.',
            }

    if rain is not None:
        penalty = round(rain * config['rain_mult'])
        penalties.append(("Rain", penalty, f"Highest hourly rain chance is {rain:g}%"))
    if wind is not None:
        penalty = min(30, round(max(0, wind - config['wind_thresh']) * 4))
        penalties.append(("Wind", penalty, f"Highest wind is {wind * MS_TO_KMH:.0f} km/h"))
    if heat is not None:
        penalty = min(30, round(max(0, heat - config['heat_thresh']) * 4))
        penalties.append(("Heat", penalty, f"Highest temperature is {heat:g}°C"))
    if visibility is not None and visibility < config['vis_thresh']:
        penalty = min(25, round((config['vis_thresh'] - visibility) / max(config['vis_thresh'] / 25, 1)))
        penalties.append(("Visibility", penalty, f"Lowest visibility is {visibility / 1000:.1f} km"))
    if config['uv_sensitive'] and uv is not None and uv >= 8:
        penalty = min(15, round((uv - 7) * 5))
        penalties.append(("UV", penalty, f"Highest UV index is {uv:g}"))
    if profile in {'construction', 'vendor', 'emergency', 'outdoor'} and thunder:
        penalties.append(("Thunderstorm", 20, "Thunderstorm codes appear in the forecast window"))
    if profile == 'farming' and thunder:
        penalties.append(("Lightning", 25, "Thunderstorm or lightning risk appears in the forecast window"))

    score = max(0, 100 - sum(p[1] for p in penalties))
    label = "Good conditions" if score >= 75 else "Moderate conditions" if score >= 45 else "Difficult conditions"
    if profile == 'fishing' and score < 45:
        label = "High-risk marine conditions"
    limiting = [reason for _, penalty, reason in penalties if penalty >= 10]
    return {
        "score": score,
        "label": label,
        "profile": profile,
        "time_window": "next_24_hours",
        "components": [{"name": name, "penalty": penalty, "reason": reason} for name, penalty, reason in penalties],
        "limiting_factors": limiting,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "This score is not an official safety certification or fishing clearance. Check official IMD and INCOIS warnings before going to sea."
            if profile == 'fishing' else
            "This score is not an official safety certification. Check official warnings before acting."
        ),
    }


def apply_official_warning_limit(score: dict | None, alerts: list | None) -> dict | None:
    """Surface an official warning as a limiting factor without changing the numeric score."""
    if not score:
        return score
    active = [alert for alert in (alerts or []) if alert]
    if not active:
        return score
    updated = dict(score)
    factors = list(updated.get('limiting_factors') or [])
    notice = 'An official weather warning is active. Official warnings take precedence over this score.'
    if notice not in factors:
        factors.insert(0, notice)
    updated['limiting_factors'] = factors
    severe = any((alert.get('severity') or '').lower() in {'severe', 'extreme', 'red'} for alert in active)
    if severe and updated.get('label') == 'Good conditions':
        updated['label'] = 'Official warning active'
    return updated


def recommendations(
    hourly: list[dict],
    profile: str,
    marine_hourly: list[dict] | None = None,
    *,
    timezone_name: str = 'Asia/Kolkata',
    official_alerts: list | None = None,
    official_status: str | None = None,
    agreement: str | None = None,
    confidence: dict | None = None,
    is_stale: bool = False,
    sources: list | None = None,
    marine_available: bool | None = None,
) -> list[dict]:
    """Occupation advice from forecast variables, local time windows, and configured rules."""
    zone = _zone(timezone_name)
    forecast_source = _forecast_source(sources)
    config = PROFILE_CONFIG.get(profile, PROFILE_CONFIG['general'])
    recs: list[dict] = []

    if is_stale:
        recs.append(_rec(
            'caution',
            'This outlook uses cached weather that may be out of date. Treat it as less certain.',
            variable='cache_freshness', time_window='cached', rule='stale_cache_limit',
            source='weather_cache', key='advice_stale',
        ))

    alerts = [alert for alert in (official_alerts or []) if alert]
    if alerts:
        top = alerts[0]
        headline = (top.get('headline') or top.get('event') or 'Official weather warning').strip()
        severity_word = (top.get('severity') or 'unknown').lower()
        rec_severity = 'warning' if severity_word in {'severe', 'extreme', 'red'} else 'caution'
        recs.append(_rec(
            rec_severity,
            f'Official warning takes precedence: {headline}. Severity: {severity_word}.',
            variable='official_warning',
            time_window=top.get('expires') or top.get('effective') or 'active',
            rule='official_warning_precedence',
            source=top.get('sender') or 'official_cap',
            key='advice_official_active',
            params={'headline': headline, 'severity': severity_word},
        ))
        blob = _alert_text(top)
        if profile == 'fishing' and any(marker in blob for marker in COASTAL_WARNING_MARKERS):
            recs.append(_rec(
                'warning',
                'Coastal or cyclone warning text is active. This is not a clearance to go to sea.',
                variable='official_warning', time_window='active', rule='fishing.cyclone_coastal',
                source=top.get('sender') or 'official_cap', key='advice_cyclone',
            ))
    elif official_status and official_status not in {'available'}:
        recs.append(_rec(
            'unknown',
            'Official warning availability is unknown. That does not mean there are no warnings.',
            variable='official_warning', time_window='unknown', rule='no_active_warning_source',
            source='official_status', key='advice_official_unknown',
        ))

    if agreement == 'sources_disagree':
        recs.append(_rec(
            'caution',
            'Weather sources disagree. Treat this outlook as less certain.',
            variable='provider_agreement', time_window='next_24_hours', rule='sources_disagree',
            source=forecast_source, key='advice_disagreement',
        ))
    confidence_score = (confidence or {}).get('score')
    if confidence_score is not None and confidence_score < 50:
        recs.append(_rec(
            'caution',
            f'Forecast agreement is low ({confidence_score}/100). Treat timing as less certain. This is not a probability.',
            variable='forecast_confidence', time_window='next_24_hours', rule='low_forecast_confidence',
            source='forecast_confidence', key='advice_low_confidence',
            params={'score': confidence_score}, value=confidence_score,
        ))

    score = weather_score(hourly, profile, marine_hourly)
    marine_missing = (
        profile == 'fishing'
        and (
            marine_available is False
            or marine_hourly is None
            or score.get('score') is None
        )
    )
    if marine_missing:
        recs.append(_rec(
            'unknown',
            'No fishing safety clearance is available. Check official IMD and INCOIS fishermen warnings and local harbour advice.',
            variable='marine_state', time_window='unavailable', rule='fishing.marine_required',
            source='marine_forecast', key='advice_marine_missing',
        ))
        recs.append(_rec(
            'information',
            'Check official warnings for your area before going out.',
            variable='official_warning', time_window='next_24_hours', rule='official_check',
            source='official_cap', key='advice_official_check',
        ))
        return recs

    if score['score'] is None:
        recs.append(_rec(
            'unknown',
            'No recommendation is available without forecast data.',
            variable='forecast', time_window='unavailable', rule='missing_forecast',
            source=forecast_source, key='advice_missing_forecast',
        ))
        return recs

    stats = _period_stats(hourly, zone)
    ranked = sorted(stats, key=lambda item: _period_penalty(item, config))
    _, rain_peak, rain_peak_hour = _extreme(hourly, 'rain_chance', zone)
    _, wind_peak, wind_peak_hour = _extreme(hourly, 'wind_ms', zone)
    _, gust_peak, gust_peak_hour = _extreme(hourly, 'wind_gust_ms', zone)
    _, heat_peak, heat_peak_hour = _extreme(hourly, 'temperature', zone)
    _, uv_peak, uv_peak_hour = _extreme(hourly, 'uv_index', zone)
    _, vis_low, vis_low_hour = _extreme(hourly, 'visibility_m', zone, pick=min)
    thunder_point = next((point for point in hourly[:24] if point.get('weather_code') in THUNDER_CODES), None)
    thunder_hour = _local(thunder_point, zone).strftime('%H:%M') if thunder_point else None

    wants_window = profile in {'general', 'farming', 'outdoor', 'tourism', 'construction', 'vendor', 'transport'}
    if wants_window and len(ranked) >= 2:
        best = ranked[0]
        later = [item for item in ranked if item['start_hour'] > best['start_hour']]
        wetter = max(later, key=lambda item: item.get('rain') or 0) if later else None
        best_rain = best.get('rain') or 0
        later_rain = (wetter.get('rain') or 0) if wetter else 0
        if wetter and later_rain >= best_rain + RAIN_RISE_DELTA:
            rise_hour, rise_value = _first_rain_rise(
                hourly, zone, wetter['start_hour'], max(RAIN_MENTION, best_rain + RAIN_RISE_DELTA),
            )
            hour = rise_hour or wetter.get('rain_hour') or f'{wetter["start_hour"]:02d}:00'
            value = rise_value if rise_value is not None else later_rain
            recs.append(_rec(
                'caution',
                f"{best['name'].capitalize()} looks more workable for outdoor work. Rain chance rises after {hour} ({value:g}%). This is a forecast, not a certainty.",
                variable='rain_chance', time_window=f'{best["window"]} vs {hour}',
                rule=f'{profile}.rain_timing', source=forecast_source, key='advice_rain_after',
                params={'period': best['name'], 'hour': hour, 'value': value}, value=value,
            ))
        elif rain_peak is not None and rain_peak >= RAIN_MENTION:
            recs.append(_rec(
                'caution',
                f'Rain chance stays near {rain_peak:g}% through this window. Highest reading is around {rain_peak_hour}. This is a forecast, not a certainty.',
                variable='rain_chance', time_window=rain_peak_hour or 'next_24_hours',
                rule=f'{profile}.rain_peak', source=forecast_source, key='advice_rain_steady',
                params={'value': rain_peak, 'hour': rain_peak_hour}, value=rain_peak,
            ))
    elif rain_peak is not None and rain_peak >= RAIN_MENTION:
        recs.append(_rec(
            'caution',
            f'Rain chance is highest at {rain_peak_hour} local time ({rain_peak:g}%). This is a forecast, not a certainty.',
            variable='rain_chance', time_window=rain_peak_hour or 'next_24_hours',
            rule=f'{profile}.rain_peak', source=forecast_source, key='advice_rain_peak',
            params={'value': rain_peak, 'hour': rain_peak_hour}, value=rain_peak,
        ))

    if profile == 'farming':
        spray = spray_window(hourly, timezone_name)
        harvest = harvest_window(hourly, timezone_name)
        if spray['suitable_hours_local']:
            hours = ', '.join(spray['suitable_hours_local'][:3])
            recs.append(_rec(
                'information',
                f'Lower rain and wind for spraying look like {hours} local time (rain ≤ 20% and wind ≤ 5 m/s). This is not crop-specific advice.',
                variable='rain_chance+wind_ms', time_window=hours, rule='farming.spray_window',
                source=forecast_source, key='advice_spray_hours', params={'hours': hours},
            ))
        else:
            recs.append(_rec(
                'caution',
                spray['message'],
                variable='rain_chance+wind_ms', time_window='next_24_hours', rule='farming.spray_window',
                source=forecast_source, key='advice_spray_none',
            ))
        if harvest['suitable_hours_local']:
            hours = ', '.join(harvest['suitable_hours_local'][:4])
            recs.append(_rec(
                'information',
                harvest['message'],
                variable='rain_chance+weather_code', time_window=hours, rule='farming.harvest_window',
                source=forecast_source, key='advice_harvest_hours', params={'hours': hours},
            ))
        else:
            recs.append(_rec(
                'caution',
                harvest['message'],
                variable='rain_chance+weather_code', time_window='next_24_hours', rule='farming.harvest_window',
                source=forecast_source, key='advice_harvest_none',
            ))

    if profile == 'fishing' and marine_hourly:
        waves = [point['wave_height_m'] for point in marine_hourly[:24] if point.get('wave_height_m') is not None]
        swells = [point['swell_height_m'] for point in marine_hourly[:24] if point.get('swell_height_m') is not None]
        if waves:
            peak = max(waves)
            if peak >= config.get('wave_thresh_m', 1.5):
                recs.append(_rec(
                    'caution',
                    f'Highest significant wave height is {peak:g} m. Model sea state looks rough. This is not a clearance to go to sea.',
                    variable='wave_height_m', time_window='next_24_hours', rule='fishing.wave_thresh',
                    source='marine_forecast', key='advice_wave', params={'value': peak}, value=peak,
                ))
            else:
                recs.append(_rec(
                    'information',
                    f'Highest significant wave height is {peak:g} m. Marine model conditions look calmer, but this is not a clearance to go to sea.',
                    variable='wave_height_m', time_window='next_24_hours', rule='fishing.wave_thresh',
                    source='marine_forecast', key='advice_wave_calm', params={'value': peak}, value=peak,
                ))
        if swells:
            peak = max(swells)
            recs.append(_rec(
                'caution' if peak >= config.get('swell_thresh_m', 2.0) else 'information',
                f'Highest swell is {peak:g} m on the marine model. Check official coastal warnings before leaving harbour.',
                variable='swell_height_m', time_window='next_24_hours', rule='fishing.swell_thresh',
                source='marine_forecast', key='advice_swell', params={'value': peak}, value=peak,
            ))

    if profile == 'tourism' and ranked:
        best = ranked[0]
        recs.append(_rec(
            'information',
            f"The less-wet outdoor window looks like {best['name']} ({best['window']}). This is a forecast, not a certainty.",
            variable='rain_chance', time_window=best['window'], rule='tourism.outdoor_window',
            source=forecast_source, key='advice_outdoor_window',
            params={'period': best['name'], 'window': best['window']},
        ))

    if thunder_hour and profile in {'farming', 'construction', 'outdoor', 'emergency', 'vendor', 'general', 'tourism'}:
        recs.append(_rec(
            'caution',
            f'Thunderstorm codes appear around {thunder_hour}. Pause exposed outdoor work then. This is a forecast, not a certainty.',
            variable='weather_code', time_window=thunder_hour, rule=f'{profile}.thunderstorm',
            source=forecast_source, key='advice_thunder', params={'hour': thunder_hour},
        ))

    if heat_peak is not None and heat_peak >= config['heat_thresh'] and profile in {
        'farming', 'construction', 'outdoor', 'vendor', 'tourism', 'general', 'emergency',
    }:
        recs.append(_rec(
            'caution',
            f'Hottest period reaches {heat_peak:g}°C around {heat_peak_hour}. Plan shade and drinking water then.',
            variable='temperature', time_window=heat_peak_hour or 'next_24_hours', rule=f'{profile}.heat_thresh',
            source=forecast_source, key='advice_heat',
            params={'value': heat_peak, 'hour': heat_peak_hour}, value=heat_peak,
        ))

    wind_over = wind_peak is not None and wind_peak >= config['wind_thresh']
    if wind_over and profile in {'farming', 'construction', 'outdoor', 'vendor', 'transport', 'fishing', 'general', 'tourism'}:
        kmh = round(wind_peak * MS_TO_KMH)
        recs.append(_rec(
            'caution',
            f'Strongest wind is {kmh} km/h around {wind_peak_hour}. Strong wind may affect outdoor work and travel.',
            variable='wind_ms', time_window=wind_peak_hour or 'next_24_hours', rule=f'{profile}.wind_thresh',
            source=forecast_source, key='advice_wind',
            params={'value': kmh, 'hour': wind_peak_hour}, value=kmh,
        ))
    if gust_peak is not None and profile in {'construction', 'outdoor', 'transport'} and (
        wind_peak is None or gust_peak >= max(wind_peak, config['wind_thresh'])
    ):
        kmh = round(gust_peak * MS_TO_KMH)
        recs.append(_rec(
            'caution',
            f'Highest gust is {kmh} km/h around {gust_peak_hour}.',
            variable='wind_gust_ms', time_window=gust_peak_hour or 'next_24_hours', rule=f'{profile}.gust',
            source=forecast_source, key='advice_gust',
            params={'value': kmh, 'hour': gust_peak_hour}, value=kmh,
        ))

    if config.get('uv_sensitive') and uv_peak is not None and uv_peak >= 8:
        recs.append(_rec(
            'caution',
            f'UV index reaches {uv_peak:g} around {uv_peak_hour}. Seek shade in the middle of the day.',
            variable='uv_index', time_window=uv_peak_hour or 'next_24_hours', rule='tourism.uv',
            source=forecast_source, key='advice_uv',
            params={'value': uv_peak, 'hour': uv_peak_hour}, value=uv_peak,
        ))

    if vis_low is not None and vis_low < config['vis_thresh'] and profile in {
        'transport', 'fishing', 'tourism', 'aviation', 'emergency', 'general',
    }:
        km = vis_low / 1000
        recs.append(_rec(
            'caution',
            f'Lowest visibility is {km:.1f} km around {vis_low_hour}. Reduced visibility may affect travel.',
            variable='visibility_m', time_window=vis_low_hour or 'next_24_hours', rule=f'{profile}.visibility',
            source=forecast_source, key='advice_visibility',
            params={'value': f'{km:.1f}', 'hour': vis_low_hour}, value=km,
        ))

    if profile == 'emergency':
        recs.insert(0 if not alerts else 1, _rec(
            'information',
            'Prioritize active official warnings and hazard information over comfort scores.',
            variable='official_warning', time_window='active', rule='emergency.official_first',
            source='official_cap', key='advice_emergency',
        ))

    profile_keys = {
        'advice_rain_after', 'advice_rain_peak', 'advice_rain_steady', 'advice_spray_hours',
        'advice_spray_none', 'advice_harvest_hours', 'advice_harvest_none', 'advice_wave',
        'advice_wave_calm', 'advice_swell', 'advice_outdoor_window', 'advice_thunder',
        'advice_heat', 'advice_wind', 'advice_gust', 'advice_uv', 'advice_visibility',
    }
    if not any(item.get('key') in profile_keys for item in recs):
        recs.append(_rec(
            'information',
            'No strong rain, heat or wind signal stands out in this window. Still check official warnings. This is a forecast, not a certainty.',
            variable='forecast', time_window='next_24_hours', rule=f'{profile}.quiet_window',
            source=forecast_source, key='advice_quiet',
        ))

    recs.append(_rec(
        'information',
        'Check official warnings for your area before going out.',
        variable='official_warning', time_window='next_24_hours', rule='official_check',
        source='official_cap', key='advice_official_check',
    ))
    return recs


def recommendations_for_bundle(hourly: list[dict], profile: str, bundle: dict, timezone_name: str) -> list[dict]:
    marine = bundle.get('marine') or {}
    return recommendations(
        hourly,
        profile,
        marine.get('hourly') if profile == 'fishing' else None,
        timezone_name=timezone_name,
        official_alerts=bundle.get('official_alerts') or bundle.get('alerts'),
        official_status=bundle.get('official_status') or bundle.get('alerts_status'),
        agreement=bundle.get('agreement'),
        confidence=bundle.get('confidence'),
        is_stale=bool(bundle.get('is_stale')),
        sources=bundle.get('sources'),
        marine_available=marine.get('available'),
    )
