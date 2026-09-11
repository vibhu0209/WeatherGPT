from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import main
from app.decision import apply_official_warning_limit, current_point, daily_summary, recommendations, weather_score
from app.main import app


NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def point(hour: int, temperature=30, rain=10, wind=3, humidity=60):
    return {
        "time": (NOW + timedelta(hours=hour)).isoformat(),
        "temperature": temperature,
        "rain_chance": rain,
        "rain_mm": 1,
        "wind_ms": wind,
        "humidity": humidity,
        "source_count": 2,
    }


def test_daily_summary_uses_location_timezone_and_real_totals():
    # Fixed UTC times that stay on the same Asia/Kolkata calendar day.
    base = datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc)
    rows = [
        {"time": base.isoformat(), "temperature": 28, "rain_chance": 10, "rain_mm": 1, "wind_ms": 3, "humidity": 60, "source_count": 2},
        {"time": (base + timedelta(hours=1)).isoformat(), "temperature": 34, "rain_chance": 10, "rain_mm": 1, "wind_ms": 3, "humidity": 60, "source_count": 2},
    ]
    day = daily_summary(rows, "Asia/Kolkata")[0]
    assert day["temperature_min"] == 28
    assert day["temperature_max"] == 34
    assert day["rain_total_mm"] == 2
    assert day["humidity_average"] == 60


def test_daily_summary_does_not_shift_utc_evening_onto_the_previous_india_date():
    # 22:00 UTC 11 Sep is 03:30 IST 12 Sep. Grouping by UTC date would be 11 Sep.
    row = {
        "time": "2026-09-11T22:00:00+00:00",
        "temperature": 30, "rain_chance": 10, "rain_mm": 1, "wind_ms": 3, "humidity": 50,
    }
    day = daily_summary([row], "Asia/Kolkata")[0]
    assert day["date"] == "2026-09-12"
    assert daily_summary([row], "UTC")[0]["date"] == "2026-09-11"


def test_current_selects_nearest_hour():
    assert current_point([point(-8), point(0), point(9)])["time"] == point(0)["time"]


def test_profile_score_is_explainable_and_bounded():
    rows = [point(i, temperature=42, rain=80, wind=14) for i in range(24)]
    farming = weather_score(rows, "farming")
    general = weather_score(rows, "general")
    assert 0 <= farming["score"] <= 100
    assert farming["score"] < general["score"]
    assert {item["name"] for item in farming["components"]} == {"Rain", "Wind", "Heat"}
    assert "not an official safety certification" in farming["disclaimer"]


def test_official_warning_limits_reassuring_score_label():
    rows = [point(i, temperature=28, rain=5, wind=2) for i in range(24)]
    score = weather_score(rows, "general")
    assert score["label"] == "Good conditions"
    limited = apply_official_warning_limit(score, [{'severity': 'severe', 'headline': 'Cyclone'}])
    assert limited["score"] == score["score"]
    assert limited["label"] == "Official warning active"
    assert any("official weather warning" in factor.lower() for factor in limited["limiting_factors"])


def test_unavailable_score_never_invents_number():
    result = weather_score([], "general")
    assert result["score"] is None
    assert result["label"] == "Unavailable"

def test_fishing_never_gets_land_weather_safety_score():
    result=weather_score([point(0)],'fishing')
    assert result['score'] is None
    assert 'Land weather cannot certify' in result['disclaimer']
    assert 'No fishing safety clearance' in recommendations([point(0)],'fishing')[0]['message']


def test_fishing_score_uses_marine_wave_penalties():
    marine = [{'wave_height_m': 3.2, 'swell_height_m': 2.5, 'time': point(0)['time']}]
    calm = weather_score([point(0)], 'fishing', [{'wave_height_m': 0.8, 'swell_height_m': 0.6, 'time': point(0)['time']}])
    rough = weather_score([point(0)], 'fishing', marine)
    assert calm['score'] is not None and rough['score'] is not None
    assert rough['score'] < calm['score']
    assert any(item['name'] == 'Waves' for item in rough['components'])
    assert 'not an official safety certification or fishing clearance' in rough['disclaimer']


def test_spray_window_is_deterministic():
    from app.decision import spray_window
    rows = [point(i, rain=10 if i < 3 else 80, wind=3) for i in range(6)]
    result = spray_window(rows, 'UTC')
    assert result['status'] == 'available'
    assert result['suitable_hours_local']


def test_recommendations_follow_thresholds():
    result = recommendations([point(0, temperature=42, rain=80, wind=14)], "outdoor")
    text = " ".join(item["message"] for item in result)
    assert "Rain" in text and "wind" in text and "shade" in text
    assert "official warnings" in text
    for item in result:
        assert item.get("variable") and item.get("rule") and item.get("source") and item.get("time_window")


def utc_hour(hour, **kwargs):
    row = point(0, **kwargs)
    row["time"] = datetime(2026, 6, 15, hour, 0, tzinfo=timezone.utc).isoformat()
    return row


def test_rain_timing_prefers_drier_morning_without_certainty():
    rows = [utc_hour(hour, rain=10 if hour < 15 else 62, temperature=30, wind=3) for hour in range(6, 22)]
    result = recommendations(rows, "construction", timezone_name="UTC")
    text = " ".join(item["message"] for item in result)
    assert "Morning" in text
    assert "15:00" in text
    assert "62" in text
    assert "certainty" in text.lower() or "forecast" in text.lower()
    assert "will rain" not in text.lower()
    rain_rec = next(item for item in result if item.get("variable") == "rain_chance")
    assert rain_rec["rule"] == "construction.rain_timing"
    assert rain_rec["key"] == "advice_rain_after"


def test_high_rain_low_confidence_does_not_claim_certainty():
    rows = [point(i, rain=85, temperature=28, wind=3) for i in range(24)]
    result = recommendations(
        rows, "general",
        confidence={"score": 28, "label": "Low agreement", "calibrated_probability": False, "reasons": []},
    )
    text = " ".join(item["message"] for item in result)
    assert "85" in text
    assert "28/100" in text
    assert "less certain" in text.lower()
    assert "probability" in text.lower()
    assert "will rain" not in text.lower()


def test_provider_disagreement_is_surfaced_with_rain():
    rows = [point(i, rain=70, temperature=28, wind=3) for i in range(24)]
    result = recommendations(rows, "transport", agreement="sources_disagree")
    text = " ".join(item["message"] for item in result)
    assert "disagree" in text.lower()
    assert "70" in text
    assert any(item["rule"] == "sources_disagree" for item in result)


def test_official_warning_leads_recommendations():
    result = recommendations(
        [point(0, rain=10)], "general",
        official_alerts=[{"headline": "Cyclone Alert", "severity": "severe", "sender": "IMD"}],
    )
    assert result[0]["variable"] == "official_warning"
    assert result[0]["rule"] == "official_warning_precedence"
    assert "Cyclone Alert" in result[0]["message"]
    assert "precedence" in result[0]["message"].lower()


def test_missing_marine_data_is_not_a_fishing_clearance():
    result = recommendations([point(0)], "fishing")
    assert result[0]["key"] == "advice_marine_missing"
    assert "No fishing safety clearance" in result[0]["message"]
    assert result[0]["source"] == "marine_forecast"


def test_stale_cached_data_is_labelled():
    result = recommendations([point(0, rain=12)], "vendor", is_stale=True)
    assert any(item["rule"] == "stale_cache_limit" for item in result)
    assert "cached" in result[0]["message"].lower() or "out of date" in result[0]["message"].lower()


def test_unknown_official_source_does_not_claim_no_warnings():
    result = recommendations(
        [point(0, rain=5)], "general", official_status="unavailable", official_alerts=[],
    )
    text = " ".join(item["message"] for item in result).lower()
    assert "does not mean there are no warnings" in text
    assert any(item["rule"] == "no_active_warning_source" for item in result)


def test_farmer_gets_harvest_and_spray_windows():
    from app.decision import harvest_window, spray_window
    rows = [utc_hour(hour, rain=8 if hour < 10 else 55, wind=2 if hour < 10 else 9) for hour in range(6, 18)]
    spray = spray_window(rows, "UTC")
    harvest = harvest_window(rows, "UTC")
    assert spray["status"] == "available"
    assert harvest["status"] == "available"
    recs = recommendations(rows, "farming", timezone_name="UTC")
    keys = {item.get("key") for item in recs}
    assert "advice_spray_hours" in keys
    assert "advice_harvest_hours" in keys


def test_tourist_uv_and_transport_visibility_are_grounded():
    rows = [utc_hour(hour, rain=20, temperature=33, wind=4) for hour in range(8, 16)]
    rows[4]["uv_index"] = 11
    rows[5]["visibility_m"] = 600
    tourist = recommendations(rows, "tourism", timezone_name="UTC")
    transport = recommendations(rows, "transport", timezone_name="UTC")
    assert any(item["variable"] == "uv_index" for item in tourist)
    assert any(item["variable"] == "visibility_m" for item in transport)


def test_fishing_rough_sea_is_not_a_clearance():
    marine = [{"wave_height_m": 3.2, "swell_height_m": 2.5, "time": utc_hour(12)["time"]}]
    recs = recommendations([utc_hour(12, rain=20, wind=9)], "fishing", marine, timezone_name="UTC")
    text = " ".join(item["message"] for item in recs).lower()
    assert "wave" in text
    assert "not a clearance" in text
    assert any(item["variable"] == "wave_height_m" for item in recs)


def test_transport_profile_penalizes_visibility():
    rows = [point(0, temperature=30, rain=10, wind=4, humidity=70)]
    rows[0]["visibility_m"] = 600
    transport = weather_score(rows, "transport")
    general = weather_score(rows, "general")
    assert transport["score"] is not None and general["score"] is not None
    assert transport["score"] < general["score"]
    assert any(item["name"] == "Visibility" for item in transport["components"])


def test_alert_endpoint_never_claims_no_warnings(monkeypatch):
    monkeypatch.setattr(main.alert_service.settings, "cap_alert_url", "")
    response = TestClient(app).get("/v1/weather/alerts?latitude=28.6&longitude=77.2")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["alerts"] == []
    assert "does not mean there are no warnings" in body["message"]
