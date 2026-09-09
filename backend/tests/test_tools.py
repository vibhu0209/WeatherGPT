import pytest
from pydantic import ValidationError

from app.models import Location
from app.tools import DailyInput, ScoreInput, TimeRangeInput, TOOL_REGISTRY, ToolResult, get_current_weather


def test_tool_registry_has_typed_models_and_callables():
    assert {
        'get_current_weather', 'get_hourly_forecast', 'get_daily_forecast', 'get_active_alerts',
        'get_weather_score', 'get_climate_summary', 'get_marine_forecast', 'get_provider_status',
        'compare_locations',
    } <= set(TOOL_REGISTRY)
    for model, function in TOOL_REGISTRY.values():
        assert hasattr(model, 'model_json_schema') and callable(function)


def test_tool_inputs_enforce_bounds_and_profiles():
    location=Location(name='Delhi',latitude=28.6,longitude=77.2)
    with pytest.raises(ValidationError): DailyInput(location=location,days=8)
    with pytest.raises(ValidationError): ScoreInput(location=location,profile='pilot')


@pytest.mark.asyncio
async def test_current_tool_preserves_provenance_and_staleness(monkeypatch):
    location=Location(name='Delhi',latitude=28.6,longitude=77.2)
    async def bundle(_):
        return {'hourly':[], 'current':None, 'retrieved_at':'2026-09-08T00:00:00+00:00', 'is_stale':True, 'sources':[]}
    monkeypatch.setattr('app.tools.service.bundle',bundle)
    result=await get_current_weather(location)
    assert isinstance(result,ToolResult)
    assert result.status=='unavailable' and result.is_stale and result.sources==[]
