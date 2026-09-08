from datetime import datetime, timezone

from app.chat import select_time_rows
from app.models import ChatRequest, Location


LOCATION = Location(name="Kolkata", latitude=22.57, longitude=88.36, timezone="Asia/Kolkata")


def _bundle():
    return {"hourly": [{"time": f"2026-09-{day:02d}T{hour:02d}:00:00+05:30", "temperature": 30} for day in range(7, 14) for hour in range(24)]}


def test_tomorrow_morning_uses_location_timezone():
    request = ChatRequest(text="weather tomorrow morning", location=LOCATION)
    rows, offset = select_time_rows(request, _bundle(), datetime(2026, 9, 7, 20, tzinfo=timezone.utc))
    assert offset == 1
    assert len(rows) == 6
    assert rows[0]["time"].startswith("2026-09-09T06")


def test_next_three_hours_is_relative_to_place_time():
    request = ChatRequest(text="rain next three hours", location=LOCATION)
    rows, _ = select_time_rows(request, _bundle(), datetime(2026, 9, 7, 20, 30, tzinfo=timezone.utc))
    assert [row["time"] for row in rows] == [
        "2026-09-08T02:00:00+05:30", "2026-09-08T03:00:00+05:30", "2026-09-08T04:00:00+05:30"
    ]


def test_weekend_selects_saturday_and_sunday():
    request = ChatRequest(text="weather this weekend", location=LOCATION)
    rows, offset = select_time_rows(request, _bundle(), datetime(2026, 9, 9, 6, tzinfo=timezone.utc))
    assert offset == 3
    assert len(rows) == 48
    assert rows[0]["time"].startswith("2026-09-12") and rows[-1]["time"].startswith("2026-09-13")
