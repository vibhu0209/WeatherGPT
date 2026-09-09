"""Typed, deterministic weather tools. These are the only weather-data boundary for a future LLM."""
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from .alerts import alert_service
from .climate import climate_service
from .decision import current_point, daily_summary, weather_score
from .marine import marine_service
from .models import Location
from .providers import PROVIDERS
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
    profile: Literal[
        'general', 'farming', 'fishing', 'outdoor', 'tourism', 'transport',
        'construction', 'emergency', 'vendor', 'aviation', 'research',
    ] = 'general'


class MarineInput(BaseModel):
    location: Location
    hours: int = Field(default=48, ge=1, le=168)


class CompareInput(BaseModel):
    locations: list[Location] = Field(min_length=2, max_length=4)
    day_offset: int = Field(default=0, ge=0, le=6)


class ClimateInput(BaseModel):
    location: Location
    metric: Literal['temperature', 'rainfall'] = 'temperature'
    years: int = Field(default=10, ge=2, le=30)


class SavedLocationsInput(BaseModel):
    locations: list[Location] = Field(default_factory=list, max_length=20)


class AlertRuleInput(BaseModel):
    channels: list[Literal['severe', 'rain', 'daily', 'forecast_change']] = Field(default_factory=lambda: ['severe'])
    enabled: bool = True
    location: Location | None = None


class AgrometInput(BaseModel):
    location: Location


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


async def get_marine_forecast(request: MarineInput) -> ToolResult:
    try:
        data = await marine_service.forecast(request.location, request.hours)
        return ToolResult(data=data, retrieved_at=data['retrieved_at'], is_stale=False, sources=data['sources'], status='available')
    except Exception:
        return ToolResult(data=None, retrieved_at=datetime.now().astimezone().isoformat(), is_stale=False, sources=[],
            status='unavailable', error='Marine forecast data is unavailable for this location.')


class ProviderStatusInput(BaseModel):
    pass


async def get_provider_status(_: ProviderStatusInput | None = None) -> ToolResult:
    now = datetime.now(timezone.utc).isoformat()
    providers = [provider(None, service.settings).health() for provider in PROVIDERS]
    return ToolResult(data={'providers': providers}, retrieved_at=now, is_stale=False,
        sources=[item['provider'] for item in providers if item.get('status') == 'available'], status='available')


async def compare_locations(request: CompareInput) -> ToolResult:
    comparisons = []
    sources: set[str] = set()
    retrieved_at = None
    for location in request.locations:
        bundle = await service.bundle(location)
        daily_rows = bundle.get('daily') or daily_summary(bundle['hourly'], location.timezone)
        day = daily_rows[request.day_offset] if len(daily_rows) > request.day_offset else None
        comparisons.append({
            'location': location.model_dump(mode='json'),
            'day_offset': request.day_offset,
            'daily': day,
            'source_count': bundle.get('source_count', 0),
            'agreement': bundle.get('agreement'),
            'retrieved_at': bundle['retrieved_at'],
            'is_stale': bundle.get('is_stale', False),
        })
        sources.update(bundle.get('sources') or [])
        retrieved_at = bundle['retrieved_at']
    return ToolResult(data={'comparisons': comparisons}, retrieved_at=retrieved_at or datetime.now().astimezone().isoformat(),
        is_stale=any(item['is_stale'] for item in comparisons), sources=sorted(sources), status='available')


async def get_saved_locations(request: SavedLocationsInput) -> ToolResult:
    now = datetime.now(timezone.utc).isoformat()
    return ToolResult(
        data={'locations': [location.model_dump(mode='json') for location in request.locations]},
        retrieved_at=now, is_stale=False, sources=['client_saved_places'],
        status='available' if request.locations else 'unavailable',
        error=None if request.locations else 'No saved locations were supplied by the client.',
    )


async def set_alert_rule(request: AlertRuleInput) -> ToolResult:
    from .rule_store import upsert_rule
    now = datetime.now(timezone.utc).isoformat()
    channels = list(dict.fromkeys(request.channels))
    location = request.location
    saved = upsert_rule(
        channels=channels,
        enabled=request.enabled,
        location_name=(location.name if location else 'selected place'),
        latitude=(location.latitude if location else 0.0),
        longitude=(location.longitude if location else 0.0),
    )
    return ToolResult(
        data={
            'channels': saved['channels'],
            'enabled': saved['enabled'],
            'location': saved['location_name'],
            'delivery': 'local_or_subscription',
            'persisted': True,
            'note': 'Official push delivery still requires device registration and configured FCM/SMS. Local notification rules are saved.',
        },
        retrieved_at=now, is_stale=False, sources=['weathergpt-rules'], status='available',
    )


async def get_agromet_advisory(request: AgrometInput) -> ToolResult:
    now = datetime.now(timezone.utc).isoformat()
    return ToolResult(
        data=None, retrieved_at=now, is_stale=False, sources=[], status='unavailable',
        error='Official IMD agromet advisory text is not connected. Use the farming weather score and local agricultural advice. Do not invent crop-specific guidance.',
    )


TOOL_REGISTRY = {
    'get_current_weather': (Location, get_current_weather),
    'get_hourly_forecast': (TimeRangeInput, get_hourly_forecast),
    'get_daily_forecast': (DailyInput, get_daily_forecast),
    'get_active_alerts': (Location, get_active_alerts),
    'get_weather_score': (ScoreInput, get_weather_score),
    'get_climate_summary': (ClimateInput, get_climate_summary),
    'get_marine_forecast': (MarineInput, get_marine_forecast),
    'get_provider_status': (ProviderStatusInput, get_provider_status),
    'compare_locations': (CompareInput, compare_locations),
    'get_saved_locations': (SavedLocationsInput, get_saved_locations),
    'set_alert_rule': (AlertRuleInput, set_alert_rule),
    'get_agromet_advisory': (AgrometInput, get_agromet_advisory),
}
