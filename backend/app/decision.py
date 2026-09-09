from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
        penalties.append(("Wind", penalty, f"Highest wind is {wind * 3.6:.0f} km/h"))
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


def recommendations(hourly: list[dict], profile: str, marine_hourly: list[dict] | None = None) -> list[dict]:
    score = weather_score(hourly, profile, marine_hourly)
    if score["score"] is None:
        if profile == 'fishing':
            return [{"severity": "unknown", "message": "No fishing safety clearance is available. Check official IMD and INCOIS fishermen warnings and local harbour advice."}]
        return [{"severity": "unknown", "message": "No recommendation is available without forecast data."}]
    messages = []
    if profile == 'fishing':
        if any(c["name"] in {"Waves", "Swell"} and c["penalty"] >= 15 for c in score["components"]):
            messages.append({"severity": "caution", "message": "Model sea state looks rough. Check official fishermen and coastal warnings before leaving harbour."})
        else:
            messages.append({"severity": "information", "message": "Marine model conditions look calmer, but this is not a clearance to go to sea."})
    if any(c["name"] == "Rain" and c["penalty"] >= 15 for c in score["components"]):
        if profile in {'transport', 'construction'}:
            messages.append({"severity": "caution", "message": "Rain may disrupt travel or construction work. Review the hourly forecast before starting."})
        elif profile == 'tourism':
            messages.append({"severity": "caution", "message": "Rain may affect sightseeing plans. Consider indoor alternatives for wetter hours."})
        elif profile == 'farming':
            spray = spray_window(hourly)
            messages.append({"severity": "caution", "message": spray['message']})
        else:
            messages.append({"severity": "caution", "message": "Rain may interrupt outdoor work. Check the hourly forecast before starting."})
    if any(c["name"] == "Wind" and c["penalty"] >= 10 for c in score["components"]):
        if profile == 'farming':
            messages.append({"severity": "caution", "message": "Strong wind may affect spraying and outdoor farm work."})
        elif profile == 'construction':
            messages.append({"severity": "caution", "message": "Strong wind may affect lifting, scaffolding and outdoor construction."})
        else:
            messages.append({"severity": "caution", "message": "Strong wind may affect outdoor work and travel."})
    if any(c["name"] == "Heat" and c["penalty"] >= 10 for c in score["components"]):
        messages.append({"severity": "caution", "message": "Plan rest, shade and drinking water during hotter hours."})
    if any(c["name"] == "Visibility" and c["penalty"] >= 10 for c in score["components"]):
        messages.append({"severity": "caution", "message": "Reduced visibility may affect travel. Allow extra time and caution."})
    if any(c["name"] in {"Thunderstorm", "Lightning"} for c in score["components"]):
        messages.append({"severity": "caution", "message": "Thunderstorm risk is present. Pause exposed outdoor work and seek safer shelter."})
    if profile == 'emergency':
        messages.insert(0, {"severity": "information", "message": "Prioritize active official warnings and hazard information over comfort scores."})
    if not messages:
        messages.append({"severity": "information", "message": "Conditions appear generally suitable based on the available forecast."})
    messages.append({"severity": "information", "message": "Check official warnings for your area before going out."})
    return messages
