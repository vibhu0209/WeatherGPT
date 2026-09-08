from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field, field_validator

from .models import Location


class MarinePoint(BaseModel):
    time: datetime
    wave_height_m: float | None = Field(default=None, ge=0, le=40)
    wave_direction: float | None = Field(default=None, ge=0, le=360)
    wave_period_s: float | None = Field(default=None, ge=0, le=40)
    swell_height_m: float | None = Field(default=None, ge=0, le=40)
    sea_surface_temperature_c: float | None = Field(default=None, ge=-5, le=45)
    @field_validator('time')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None: raise ValueError('Marine timestamp must include timezone')
        return value.astimezone(timezone.utc)


class MarineService:
    endpoint = 'https://marine-api.open-meteo.com/v1/marine'

    async def forecast(self, location: Location, hours: int = 48) -> dict:
        params = {'latitude':location.latitude, 'longitude':location.longitude, 'timezone':'UTC',
            'forecast_hours':hours, 'cell_selection':'sea',
            'hourly':'wave_height,wave_direction,wave_period,swell_wave_height,sea_surface_temperature'}
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            response = await client.get(self.endpoint, params=params)
            response.raise_for_status()
        data = response.json()
        hourly = data.get('hourly') or {}
        rows = []
        for index, value in enumerate(hourly.get('time') or []):
            def field(name):
                values = hourly.get(name) or []
                return values[index] if index < len(values) else None
            point = MarinePoint(time=datetime.fromisoformat(value).replace(tzinfo=timezone.utc),
                wave_height_m=field('wave_height'), wave_direction=field('wave_direction'),
                wave_period_s=field('wave_period'), swell_height_m=field('swell_wave_height'),
                sea_surface_temperature_c=field('sea_surface_temperature'))
            if any(getattr(point, name) is not None for name in ('wave_height_m','wave_period_s','swell_height_m')):
                rows.append(point.model_dump(mode='json'))
        if not rows:
            raise ValueError('Marine forecast is unavailable for this location. Choose a point at sea near the harbour.')
        return {'location':location.model_dump(), 'hourly':rows, 'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'is_stale':False, 'sources':['Open-Meteo Marine API'],
            'limitations':['Model guidance only; not suitable for coastal navigation.',
                'Official IMD and INCOIS fishermen, cyclone and sea-state warnings take precedence.']}


marine_service = MarineService()
