from datetime import datetime, timezone

from app.risks import estimate_risks


TIME = datetime.now(timezone.utc).isoformat()


def test_each_threshold_has_explicit_non_official_classification():
    risks = estimate_risks([{"time":TIME,"rain_mm":16,"wind_ms":14,"temperature":41,"visibility_m":500}])
    assert {risk["kind"] for risk in risks} == {"heavy_rain","strong_wind","heat","poor_visibility"}
    assert all(risk["classification"] == "WEATHERGPT_RISK_ESTIMATE" for risk in risks)
    assert all("not an official government warning" in risk["disclaimer"] for risk in risks)


def test_values_below_threshold_produce_no_risk():
    assert estimate_risks([{"time":TIME,"rain_mm":2,"wind_ms":3,"temperature":30,"visibility_m":5000}]) == []


def test_missing_data_does_not_create_risk():
    assert estimate_risks([{"time":TIME}]) == []
