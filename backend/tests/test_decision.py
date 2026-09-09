from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.decision import current_point, daily_summary, recommendations, weather_score
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
    rows = [point(0, 28), point(1, 34)]
    day = daily_summary(rows, "Asia/Kolkata")[0]
    assert day["temperature_min"] == 28
    assert day["temperature_max"] == 34
    assert day["rain_total_mm"] == 2
    assert day["humidity_average"] == 60


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


def test_unavailable_score_never_invents_number():
    result = weather_score([], "general")
    assert result["score"] is None
    assert result["label"] == "Unavailable"

def test_fishing_never_gets_land_weather_safety_score():
    result=weather_score([point(0)],'fishing')
    assert result['score'] is None
    assert 'Land weather cannot certify' in result['disclaimer']
    assert 'No fishing safety clearance' in recommendations([point(0)],'fishing')[0]['message']


def test_recommendations_follow_thresholds():
    result = recommendations([point(0, temperature=42, rain=80, wind=14)], "outdoor")
    text = " ".join(item["message"] for item in result)
    assert "Rain" in text and "wind" in text and "shade" in text
    assert "official warnings" in text


def test_transport_profile_penalizes_visibility():
    rows = [point(0, temperature=30, rain=10, wind=4, humidity=70)]
    rows[0]["visibility_m"] = 600
    transport = weather_score(rows, "transport")
    general = weather_score(rows, "general")
    assert transport["score"] is not None and general["score"] is not None
    assert transport["score"] < general["score"]
    assert any(item["name"] == "Visibility" for item in transport["components"])


def test_alert_endpoint_never_claims_no_warnings():
    response = TestClient(app).get("/v1/weather/alerts?latitude=28.6&longitude=77.2")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["alerts"] == []
    assert "does not mean there are no warnings" in body["message"]
