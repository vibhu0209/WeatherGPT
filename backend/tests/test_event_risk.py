from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.chat import parse_hour_window
from app.chat_tools import select_tool
from app.event_risk import (
    assess_timed_event_risk, is_event_question, is_heavy_rain_or_flood_question,
    is_why_question, parse_clock_point, why_weather_brief,
)
from app.models import ChatRequest, Location


LOC = Location(name='Mumbai', latitude=19.07, longitude=72.87, timezone='Asia/Kolkata')
ZONE = ZoneInfo('Asia/Kolkata')


def test_parse_at_4_pm_window():
    now = datetime(2026, 9, 14, 10, 0, tzinfo=ZONE)
    start, end = parse_hour_window('outdoor event at 4 PM in Mumbai', 'Asia/Kolkata', now)
    assert start is not None and end is not None
    assert start.hour == 15
    assert end.hour == 18
    point = parse_clock_point('at 4 PM', 'Asia/Kolkata', now)
    assert point is not None and point.hour == 16


def test_event_and_flood_detectors():
    assert is_event_question('I have an outdoor event at 4 PM')
    assert is_heavy_rain_or_flood_question('exact risks of heavy rainfall')
    assert is_why_question('why is it raining today?')
    assert not is_heavy_rain_or_flood_question('will it be sunny')


def test_event_routes_to_hourly():
    assert select_tool(ChatRequest(
        text='I have an outdoor event at 4 PM in Mumbai; what are the risks of heavy rainfall?',
        location=LOC,
    )) == 'get_hourly_forecast'


def test_timed_event_risk_escalates_with_heavy_rain():
    rows = [
        {'rain_chance': 80, 'rain_mm': 12, 'wind_ms': 3, 'temperature': 30},
        {'rain_chance': 70, 'rain_mm': 10, 'wind_ms': 4, 'temperature': 29},
    ]
    high = assess_timed_event_risk(rows, place='Mumbai', window_label='3–6 PM')
    assert high['severity'] in {'high', 'elevated'}
    assert 'not a flood model' in high['disclaimer'].lower()
    assert 'radar' not in high['decision'].lower()
    low = assess_timed_event_risk(
        [{'rain_chance': 5, 'rain_mm': 0, 'wind_ms': 2, 'temperature': 28}],
        place='Mumbai', window_label='3–6 PM',
    )
    assert low['severity'] == 'lower'


def test_why_brief_uses_disagreement_and_alerts():
    alert_line = why_weather_brief({
        'official_alerts': [{'headline': 'Heavy rain warning', 'event': 'Rain'}],
        'disagreement_reasons': [],
        'sources': ['open-meteo'],
    })
    assert alert_line and 'official warning' in alert_line.lower()
    disagree = why_weather_brief({
        'official_alerts': [],
        'agreement': 'sources_disagree',
        'disagreement_reasons': ['Rain timing differs across providers'],
        'sources': ['open-meteo', 'weatherapi'],
        'source_count': 2,
    })
    assert disagree and 'uncertain' in disagree.lower()


def test_layperson_keeps_why_and_radar_honesty():
    from app.layperson import format_layperson_answer
    raw = (
        'Yes — rain is likely in this window. Plan as if it will rain.\n\n'
        'Why this reading is steadier: 2 sources broadly agree (open-meteo, weatherapi).\n\n'
        'Mumbai · 2026-09-14\n\n'
        'Temperature: 25 to 30\n\n'
        'Live weather radar is not available in WeatherGPT yet — this answer uses verified hourly forecasts only.\n\n'
        'Check official warnings before going out.'
    )
    out = format_layperson_answer(raw)
    assert 'Why this reading' in out
    assert 'radar is not available' in out.lower()
    assert out.lower().startswith('yes')
