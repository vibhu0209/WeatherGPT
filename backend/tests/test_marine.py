import httpx
import pytest
from pydantic import ValidationError

from app.marine import MarinePoint, MarineService
from app.models import Location


@pytest.mark.asyncio
async def test_marine_normalizes_validated_model_data(monkeypatch):
    payload={'hourly':{'time':['2026-09-08T00:00'],'wave_height':[1.4],'wave_direction':[210],
        'wave_period':[8.2],'swell_wave_height':[1.0],'sea_surface_temperature':[28.5]}}
    async def handler(request):
        assert request.url.params['cell_selection']=='sea'
        return httpx.Response(200,json=payload)
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler)))
    result=await MarineService().forecast(Location(name='Harbour',latitude=15,longitude=73),24)
    assert result['hourly'][0]['wave_height_m']==1.4
    assert 'not suitable for coastal navigation' in result['limitations'][0]


def test_marine_rejects_impossible_values():
    with pytest.raises(ValidationError): MarinePoint(time='2026-09-08T00:00:00Z',wave_height_m=-1)
