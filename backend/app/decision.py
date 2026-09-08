from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


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


def weather_score(hourly: list[dict], profile: str) -> dict:
    if profile == 'fishing':
        return {
            'score':None, 'label':'Marine safety score unavailable', 'profile':profile,
            'components':[], 'limiting_factors':['Wave, sea-state and official fishermen warning inputs are required'],
            'disclaimer':'Land weather cannot certify that fishing is safe. Check official IMD and INCOIS warnings.'}
    future = hourly[:24]
    if not future:
        return {
            "score": None,
            "label": "Unavailable",
            "profile": profile,
            "components": [],
            "limiting_factors": ["Forecast data is unavailable"],
            "disclaimer": "This score is not an official safety certification.",
        }

    rain = max((p["rain_chance"] for p in future if p.get("rain_chance") is not None), default=None)
    wind = max((p["wind_ms"] for p in future if p.get("wind_ms") is not None), default=None)
    heat = max((p["temperature"] for p in future if p.get("temperature") is not None), default=None)
    penalties: list[tuple[str, int, str]] = []

    if rain is not None:
        multiplier = 0.45 if profile in {"farming", "outdoor"} else 0.30
        penalty = round(rain * multiplier)
        penalties.append(("Rain", penalty, f"Highest hourly rain chance is {rain:g}%"))
    if wind is not None:
        threshold = 5 if profile == "farming" else 8
        penalty = min(30, round(max(0, wind - threshold) * 4))
        penalties.append(("Wind", penalty, f"Highest wind is {wind * 3.6:.0f} km/h"))
    if heat is not None:
        threshold = 34 if profile in {"outdoor", "farming"} else 37
        penalty = min(30, round(max(0, heat - threshold) * 4))
        penalties.append(("Heat", penalty, f"Highest temperature is {heat:g}°C"))

    score = max(0, 100 - sum(p[1] for p in penalties))
    label = "Good conditions" if score >= 75 else "Moderate conditions" if score >= 45 else "Difficult conditions"
    limiting = [reason for _, penalty, reason in penalties if penalty >= 10]
    return {
        "score": score,
        "label": label,
        "profile": profile,
        "time_window": "next_24_hours",
        "components": [{"name": name, "penalty": penalty, "reason": reason} for name, penalty, reason in penalties],
        "limiting_factors": limiting,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "This score is not an official safety certification. Check official warnings before acting.",
    }


def recommendations(hourly: list[dict], profile: str) -> list[dict]:
    score = weather_score(hourly, profile)
    if score["score"] is None:
        if profile=='fishing': return [{"severity":"unknown","message":"No fishing safety clearance is available. Check official IMD and INCOIS fishermen warnings and local harbour advice."}]
        return [{"severity": "unknown", "message": "No recommendation is available without forecast data."}]
    messages = []
    if any(c["name"] == "Rain" and c["penalty"] >= 15 for c in score["components"]):
        messages.append({"severity": "caution", "message": "Rain may interrupt outdoor work. Check the hourly forecast before starting."})
    if any(c["name"] == "Wind" and c["penalty"] >= 10 for c in score["components"]):
        messages.append({"severity": "caution", "message": "Strong wind may affect outdoor work and spraying."})
    if any(c["name"] == "Heat" and c["penalty"] >= 10 for c in score["components"]):
        messages.append({"severity": "caution", "message": "Plan rest, shade and drinking water during hotter hours."})
    if not messages:
        messages.append({"severity": "information", "message": "Conditions appear generally suitable based on the available forecast."})
    messages.append({"severity": "information", "message": "Check official warnings for your area before going out."})
    return messages
