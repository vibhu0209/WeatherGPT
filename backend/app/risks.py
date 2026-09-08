from datetime import datetime, timezone


def estimate_risks(hourly: list[dict]) -> list[dict]:
    """Create transparent local risk estimates; never official warnings."""
    future = hourly[:24]
    if not future:
        return []

    rules = [
        ("heavy_rain", "Heavy rain may affect travel or outdoor work", "rain_mm", 15, "orange", "15 mm or more in one forecast hour"),
        ("strong_wind", "Strong wind may affect outdoor work", "wind_ms", 13.9, "orange", "50 km/h or stronger forecast wind"),
        ("heat", "High temperature may increase heat stress", "temperature", 40, "orange", "40°C or higher forecast temperature"),
        ("poor_visibility", "Poor visibility may affect travel", "visibility_m", 1000, "yellow", "Visibility below 1 km"),
    ]
    output = []
    for kind, message, field, threshold, severity, rationale in rules:
        candidates = [p for p in future if p.get(field) is not None]
        if field == "visibility_m":
            matches = [p for p in candidates if p[field] < threshold]
        else:
            matches = [p for p in candidates if p[field] >= threshold]
        if not matches:
            continue
        point = matches[0]
        output.append({
            "id": f"risk-{kind}-{point['time']}",
            "classification": "WEATHERGPT_RISK_ESTIMATE",
            "kind": kind,
            "severity": severity,
            "message": message,
            "valid_at": point["time"],
            "supporting_value": point[field],
            "unit": {"rain_mm":"mm","wind_ms":"m/s","temperature":"°C","visibility_m":"m"}[field],
            "rationale": rationale,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": "WeatherGPT Risk Estimate — not an official government warning.",
        })
    return output
