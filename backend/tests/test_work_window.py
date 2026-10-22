from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.decision import harvest_window, recommendations, spray_window
from app.main import app
from app.models import ChatRequest, Location
from app.tools import WorkWindowInput, get_work_window
from app.work_window import (
    UnsupportedActivityError,
    format_work_window_answer,
    plan_from_bundle,
    plan_work_windows,
)

LOC = Location(name='Delhi', latitude=28.6, longitude=77.2, timezone='UTC')
NOW = datetime(2026, 6, 15, 5, 0, tzinfo=timezone.utc)


def hour(clock, rain=10, wind=3.0, code=1, **extra):
    stamp = datetime(2026, 6, 15, clock, 0, tzinfo=timezone.utc)
    row = {
        'time': stamp.isoformat(),
        'temperature': 28,
        'rain_chance': rain,
        'rain_mm': 0.0,
        'wind_ms': wind,
        'humidity': 55,
        'weather_code': code,
    }
    row.update(extra)
    return row


def test_a_four_hour_spray_happy_path_exclusive_end():
    rows = [
        hour(6, rain=10, wind=3),
        hour(7, rain=8, wind=2),
        hour(8, rain=12, wind=4),
        hour(9, rain=5, wind=3),
        hour(10, rain=80, wind=3),
        hour(11, rain=90, wind=4),
        hour(12, rain=70, wind=4),
    ]
    plan = plan_work_windows(rows, 'spray', 'UTC', now=NOW)
    assert plan['status'] == 'available'
    assert len(plan['work_windows']) == 1
    window = plan['best_window']
    assert window['start_local'] == '2026-06-15T06:00:00+00:00'
    assert window['end_local'] == '2026-06-15T10:00:00+00:00'
    assert window['duration_hours'] == 4
    assert plan['avoid_windows'][0]['start_local'] == '2026-06-15T10:00:00+00:00'
    spoken = format_work_window_answer(plan, 'spray')
    assert spoken.startswith('Your best spray window is 06:00–10:00 local time (4 hours).')
    assert 'Avoid 10:00' in spoken


def test_b_missing_hour_gap_splits_run():
    rows = [hour(6), hour(7), hour(9), hour(10)]
    plan = plan_work_windows(rows, 'spray', 'UTC', now=NOW)
    starts = [item['start_local'] for item in plan['work_windows']]
    ends = [item['end_local'] for item in plan['work_windows']]
    assert starts == ['2026-06-15T06:00:00+00:00', '2026-06-15T09:00:00+00:00']
    assert ends == ['2026-06-15T08:00:00+00:00', '2026-06-15T11:00:00+00:00']
    assert all(item['duration_hours'] == 2 for item in plan['work_windows'])
    assert not any(item['start_local'] <= '2026-06-15T08:00:00+00:00' < item['end_local']
                   and item['start_local'] < '2026-06-15T08:00:00+00:00' < item['end_local']
                   and item['duration_hours'] >= 3 for item in plan['work_windows'])


def test_missing_timestamp_and_duplicate_timestamp_break_runs():
    missing_timestamp = [hour(6), {**hour(7), 'time': None}, hour(7), hour(8)]
    missing_plan = plan_work_windows(missing_timestamp, 'spray', 'UTC', now=NOW)
    assert missing_plan['work_windows'] == [
        {
            'start_local': '2026-06-15T07:00:00+00:00',
            'end_local': '2026-06-15T09:00:00+00:00',
            'duration_hours': 2,
        }
    ]

    duplicate_timestamp = [hour(6), hour(7), hour(7), hour(8)]
    duplicate_plan = plan_work_windows(duplicate_timestamp, 'spray', 'UTC', now=NOW)
    assert [window['duration_hours'] for window in duplicate_plan['work_windows']] == [2]
    assert duplicate_plan['best_window']['end_local'] == '2026-06-15T08:00:00+00:00'


def test_c_run_shorter_than_minimum_is_dropped():
    rows = [hour(6), hour(8), hour(9)]
    plan = plan_work_windows(rows, 'spray', 'UTC', min_hours=2, now=NOW)
    assert [item['duration_hours'] for item in plan['work_windows']] == [2]
    assert plan['best_window']['start_local'] == '2026-06-15T08:00:00+00:00'
    short_only = plan_work_windows([hour(6)], 'spray', 'UTC', now=NOW)
    assert short_only['work_windows'] == []
    assert short_only['best_window'] is None
    assert short_only['status'] == 'available'


def test_d_all_wet_forecast_is_available_without_windows():
    rows = [hour(clock, rain=90, wind=8) for clock in range(6, 14)]
    plan = plan_work_windows(rows, 'spray', 'UTC', now=NOW)
    assert plan['status'] == 'available'
    assert plan['work_windows'] == []
    assert plan['best_window'] is None
    assert plan['message']
    assert plan['avoid_windows']
    assert plan['avoid_windows'][0]['reason'] == 'high rain probability'


def test_e_empty_hourly_is_unavailable():
    plan = plan_work_windows([], 'spray', 'UTC', now=NOW)
    assert plan['status'] == 'unavailable'
    assert plan['work_windows'] == []
    assert plan['best_window'] is None
    assert plan['avoid_windows'] == []
    assert 'cannot be determined' in plan['message']


def test_f_unsupported_activity_is_rejected():
    with pytest.raises(UnsupportedActivityError):
        plan_work_windows([hour(6)], 'irrigate', 'UTC', now=NOW)
    with pytest.raises(ValidationError):
        WorkWindowInput(location=LOC, activity='irrigate')


def test_longest_window_wins_then_earliest_on_tie():
    rows = [
        hour(6), hour(7),
        hour(9), hour(10), hour(11),
        hour(13, rain=10, wind=3), hour(14, rain=10, wind=3), hour(15, rain=10, wind=3),
    ]
    plan = plan_work_windows(rows, 'spray', 'UTC', now=NOW)
    assert plan['best_window']['duration_hours'] == 3
    assert plan['best_window']['start_local'] == '2026-06-15T09:00:00+00:00'
    tied = [hour(6), hour(7), hour(10), hour(11)]
    tie_plan = plan_work_windows(tied, 'spray', 'UTC', now=NOW)
    assert tie_plan['best_window']['start_local'] == '2026-06-15T06:00:00+00:00'


def test_avoid_rain_threshold_thunder_and_combined():
    rain_only = plan_work_windows(
        [hour(6, rain=60, wind=9, code=1), hour(7, rain=61, wind=9, code=1)],
        'spray', 'UTC', now=NOW,
    )
    assert rain_only['avoid_windows'][0]['reason'] == 'high rain probability'
    thunder = plan_work_windows(
        [hour(6, rain=10, wind=9, code=95), hour(7, rain=10, wind=9, code=96)],
        'harvest', 'UTC', now=NOW,
    )
    assert thunder['avoid_windows'][0]['reason'] == 'thunderstorm conditions'
    both = plan_work_windows(
        [hour(6, rain=80, wind=9, code=99)],
        'spray', 'UTC', now=NOW,
    )
    assert 'rain' in both['avoid_windows'][0]['reason']
    assert 'thunder' in both['avoid_windows'][0]['reason']


def test_unknown_weather_code_does_not_mean_no_avoid_condition():
    plan = plan_work_windows(
        [hour(6, rain=10, wind=3, code=None), hour(7, rain=10, wind=3, code=None)],
        'spray', 'UTC', now=NOW,
    )
    assert plan['avoid_windows'] == []


def test_missing_required_field_breaks_a_run():
    rows = [hour(6), {**hour(7), 'wind_ms': None}, hour(8), hour(9)]
    plan = plan_work_windows(rows, 'spray', 'UTC', now=NOW)
    assert plan['work_windows'][0]['duration_hours'] == 2
    assert plan['work_windows'][0]['start_local'] == '2026-06-15T08:00:00+00:00'


def test_horizon_truncates_at_48_hours():
    start = datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc)
    rows = [{
        'time': (start + timedelta(hours=index)).isoformat(),
        'rain_chance': 10, 'wind_ms': 3, 'weather_code': 1,
    } for index in range(50)]
    plan = plan_work_windows(rows, 'spray', 'UTC', now=NOW)
    assert plan['best_window']['duration_hours'] == 48


def test_timezone_offset_appears_on_local_bounds():
    rows = [hour(6), hour(7)]
    plan = plan_work_windows(rows, 'spray', 'Asia/Kolkata', now=NOW)
    assert plan['best_window']['start_local'].endswith('+05:30')
    assert 'T11:30:00+05:30' in plan['best_window']['start_local']
    assert 'T13:30:00+05:30' in plan['best_window']['end_local']


def test_harvest_reuses_existing_thresholds():
    qualifying = [hour(6, rain=25, wind=7, code=1), hour(7, rain=30, wind=8, code=2)]
    failing = [hour(6, rain=31, wind=1, code=1), hour(7, rain=10, wind=1, code=95)]
    ok = plan_work_windows(qualifying, 'harvest', 'UTC', now=NOW)
    no = plan_work_windows(failing, 'harvest', 'UTC', now=NOW)
    assert ok['best_window']['duration_hours'] == 2
    assert no['best_window'] is None
    legacy = harvest_window(qualifying, 'UTC')
    assert legacy['suitable_hours_local']


def test_existing_spray_harvest_recommendations_unchanged():
    rows = [hour(clock, rain=10 if clock < 10 else 80, wind=3) for clock in range(6, 14)]
    spray = spray_window(rows, 'UTC')
    harvest = harvest_window(rows, 'UTC')
    recs = recommendations(rows, 'farming', timezone_name='UTC')
    assert spray['status'] == 'available'
    assert 'suitable_hours_local' in spray
    assert harvest['status'] == 'available'
    keys = {item.get('key') for item in recs}
    assert 'advice_spray_hours' in keys
    assert 'advice_harvest_hours' in keys


def test_stale_and_official_alert_honesty():
    rows = [hour(6), hour(7)]
    stale = plan_from_bundle(
        {'hourly': rows, 'is_stale': True, 'sources': ['open-meteo']},
        'spray', 'UTC', now=NOW,
        official_status='unavailable', official_alerts=[], official_message='feed down',
    )
    text = format_work_window_answer(stale, 'spray')
    assert stale['is_stale'] is True
    assert 'saved earlier' in text.lower()
    assert 'could not be verified' in text
    assert 'no warnings' in text.lower()
    active = plan_from_bundle(
        {'hourly': rows, 'is_stale': False, 'sources': ['open-meteo']},
        'spray', 'UTC', now=NOW,
        official_status='available',
        official_alerts=[{'headline': 'Red rain warning', 'severity': 'severe'}],
    )
    active_text = format_work_window_answer(active, 'spray')
    assert 'Red rain warning' in active_text
    assert 'take precedence' in active_text.lower()
    assert 'crop-specific' in active_text.lower()


@pytest.mark.asyncio
async def test_get_work_window_tool_uses_bundle_and_rejects_bad_activity(monkeypatch):
    async def bundle(_):
        return {
            'hourly': [hour(6), hour(7), hour(8), hour(9), hour(10, rain=80)],
            'retrieved_at': NOW.isoformat(),
            'is_stale': True,
            'sources': ['open-meteo'],
        }

    async def official(_):
        return {'status': 'available', 'alerts': [], 'message': 'available'}

    monkeypatch.setattr('app.tools.service.bundle', bundle)
    monkeypatch.setattr('app.tools.alert_service.official', official)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    monkeypatch.setattr('app.work_window.datetime', FrozenDateTime)

    result = await get_work_window(WorkWindowInput(location=LOC, activity='spray'))
    assert result.is_stale is True
    assert result.sources == ['open-meteo']
    assert result.data['best_window']['duration_hours'] == 4
    assert result.data['status'] == 'available'


def test_work_window_route_and_validation(monkeypatch):
    async def weather(_):
        return {
            'hourly': [hour(6), hour(7), hour(8), hour(9), hour(10, rain=75)],
            'retrieved_at': NOW.isoformat(),
            'is_stale': False,
            'sources': ['open-meteo'],
            'source_count': 1,
            'agreement': 'single_source',
            'location': LOC.model_dump(mode='json'),
        }

    async def official(_):
        return {'status': 'unavailable', 'alerts': [], 'message': 'not connected'}

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    monkeypatch.setattr('app.main.service.bundle', weather)
    monkeypatch.setattr('app.main.alert_service.official', official)
    monkeypatch.setattr('app.work_window.datetime', FrozenDateTime)

    client = TestClient(app)
    ok = client.get('/v1/weather/work-window?latitude=28.6&longitude=77.2&activity=spray&timezone=UTC')
    assert ok.status_code == 200
    body = ok.json()
    assert body['best_window']['duration_hours'] == 4
    assert body['best_window']['end_local'] == '2026-06-15T10:00:00+00:00'
    assert body['is_stale'] is False
    assert body['official_status'] == 'unavailable'

    bad = client.get('/v1/weather/work-window?latitude=28.6&longitude=77.2&activity=irrigate&timezone=UTC')
    assert bad.status_code == 422
    payload = bad.json()
    assert payload['code'] == 'validation_error'
    assert payload['retryable'] is False


def test_chat_spray_and_harvest_use_planner(monkeypatch):
    from app.chat import answer
    from app.chat_tools import select_tool

    assert select_tool(ChatRequest(text='When can I spray tomorrow?', location=LOC)) == 'get_work_window'
    assert select_tool(ChatRequest(text='What is the best time to spray?', location=LOC)) == 'get_work_window'
    assert select_tool(ChatRequest(text='When should I spray weedicide?', location=LOC)) == 'get_work_window'
    assert select_tool(ChatRequest(text='When can I harvest tomorrow?', location=LOC)) == 'get_work_window'
    assert select_tool(ChatRequest(text='When should I harvest?', location=LOC)) == 'get_work_window'
    assert select_tool(ChatRequest(text='Will it rain today?', location=LOC)) == 'get_hourly_forecast'

    bundle = {
        'hourly': [hour(6), hour(7), hour(8), hour(9), hour(10, rain=80)],
        'is_stale': True,
        'retrieved_at': NOW.isoformat(),
        'sources': ['open-meteo'],
        'official_status': 'available',
        'official_alerts': [{'headline': 'Heat wave', 'severity': 'moderate'}],
        'alerts': [{'headline': 'Heat wave', 'severity': 'moderate'}],
        'agreement': 'single_source',
    }

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    monkeypatch.setattr('app.work_window.datetime', FrozenDateTime)
    spray = answer(ChatRequest(text='When can I spray tomorrow?', location=LOC), bundle)['answer']
    weedicide = answer(ChatRequest(text='When should I spray weedicide?', location=LOC), bundle)['answer']
    harvest = answer(ChatRequest(text='When should I harvest?', location=LOC), bundle)['answer']
    assert spray.startswith('Showing weather saved earlier')
    assert 'Your best spray window is 06:00–10:00 local time (4 hours).' in spray
    assert 'Your best spray window is 06:00–10:00 local time (4 hours).' in weedicide
    assert 'Avoid 10:00' in spray
    assert 'Heat wave' in spray
    assert 'take precedence' in spray.lower()
    assert 'crop-specific' in spray.lower()
    assert 'Your best harvest window is 06:00–10:00 local time (4 hours).' in harvest
