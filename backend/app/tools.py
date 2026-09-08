"""Typed, deterministic weather tools. These are the only weather-data boundary for a future LLM."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .alerts import alert_service
from .climate import climate_service
from .decision import current_point, daily_summary, weather_score
from .models import Location
from .weather import service


class TimeRangeInput(BaseModel):
    location: Location
    start: datetime | None = None
    end: datetime | None = None


class DailyInput(BaseModel):
    location: Location
    days: int = Field(default=7, ge=1, le=7)


class ScoreInput(BaseModel):
    location: Location
    profile: Literal['general', 'farming', 'fishing', 'outdoor'] = 'general'


class ClimateInput(BaseModel):
    location: Location
    metric: Literal['temperature', 'rainfall'] = 'temperature'
    years: int = Field(default=10, ge=2, le=30)


class ToolResult(BaseModel):
    data: Any
    retrieved_at: str
    is_stale: bool
    sources: list[str]
    status: Literal['available', 'unavailable'] = 'available'
    error: str | None = None


def _result(bundle: dict, data: Any) -> ToolResult:
    status = 'available' if data is not None and data != [] else 'unavailable'
    return ToolResult(data=data, retrieved_at=bundle['retrieved_at'], is_stale=bundle['is_stale'],
        sources=bundle['sources'], status=status,
        error=None if status == 'available' else 'Validated weather data is unavailable for this request.')


async def get_current_weather(location: Location) -> ToolResult:
    bundle = await service.bundle(location)
    return _result(bundle, bundle.get('current') or current_point(bundle['hourly']))


async def get_hourly_forecast(request: TimeRangeInput) -> ToolResult:
    bundle = await service.bundle(request.location)
    rows = [row for row in bundle['hourly'] if
        (request.start is None or datetime.fromisoformat(row['time']) >= request.start) and
        (request.end is None or datetime.fromisoformat(row['time']) <= request.end)]
    return _result(bundle, rows)


async def get_daily_forecast(request: DailyInput) -> ToolResult:
    bundle = await service.bundle(request.location)
    rows = bundle.get('daily') or daily_summary(bundle['hourly'], request.location.timezone)
    return _result(bundle, rows[:request.days])


async def get_active_alerts(location: Location) -> ToolResult:
    official = await alert_service.official(location)
    now = datetime.now().astimezone().isoformat()
    return ToolResult(data=official['alerts'], retrieved_at=now, is_stale=False, sources=['configured CAP authority'] if official['status']=='available' else [],
        status=official['status'], error=official['message'])


async def get_weather_score(request: ScoreInput) -> ToolResult:
    bundle = await service.bundle(request.location)
    score = bundle.get('scores', {}).get(request.profile) or weather_score(bundle['hourly'], request.profile)
    return _result(bundle, score)


async def get_climate_summary(request: ClimateInput) -> ToolResult:
    data = await climate_service.summary(request.location, request.metric, request.years)
    return ToolResult(data=data, retrieved_at=data['generated_at'], is_stale=False, sources=[data['source']])


TOOL_REGISTRY = {
    'get_current_weather': (Location, get_current_weather),
    'get_hourly_forecast': (TimeRangeInput, get_hourly_forecast),
    'get_daily_forecast': (DailyInput, get_daily_forecast),
    'get_active_alerts': (Location, get_active_alerts),
    'get_weather_score': (ScoreInput, get_weather_score),
    'get_climate_summary': (ClimateInput, get_climate_summary),
}
