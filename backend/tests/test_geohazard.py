from app.geohazard import rainfall_totals_mm, score_hazard
from app.chat_tools import select_tool
from app.models import ChatRequest, Location


LOC = Location(name='Joshimath', latitude=30.55, longitude=79.56)


def test_rainfall_totals_sum_verified_hours():
    hourly = [{'rain_mm': 10}, {'rain_mm': 5}, {'rain_mm': None}, {'rain_mm': 2}]
    assert rainfall_totals_mm(hourly, 4) == 17.0
    assert rainfall_totals_mm([], 24) is None


def test_hazard_score_escalates_with_rain_soil_slope():
    low = score_hazard(5, 5, 0.2, 3, False)
    assert low['severity'] == 'green'
    high = score_hazard(110, 150, 0.45, 30, True)
    assert high['severity'] == 'red'
    assert high['score'] >= 55
    assert any('Official warning' in item for item in high['factors'])


def test_landslide_question_routes_to_hazard_tool():
    assert select_tool(ChatRequest(
        text='Given this rainfall, soil moisture and terrain, will this road collapse into a landslide?',
        location=LOC,
        profile='emergency',
    )) == 'assess_infrastructure_hazard'
