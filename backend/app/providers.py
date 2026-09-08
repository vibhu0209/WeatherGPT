"""Provider adapters normalize validated values; missing fields remain null."""
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import httpx
from .models import Forecast, Point, Location, Settings

class WeatherProvider(ABC):
    id = ''
    display_name = ''
    model_family = ''
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client, self.settings = client, settings
    @property
    def enabled(self): return True
    def capabilities(self):
        return {'current':True, 'hourly':True, 'daily':True, 'alerts':False, 'historical':False}
    def health(self):
        return {'provider':self.id, 'display_name':self.display_name, 'enabled':self.enabled,
            'status':'configured' if self.enabled else 'not_configured', 'capabilities':self.capabilities()}
    @abstractmethod
    async def forecast(self, loc: Location) -> Forecast: ...
    async def get_current(self, loc: Location):
        forecast = await self.forecast(loc)
        return forecast.hourly[0] if forecast.hourly else None
    async def get_hourly(self, loc: Location, start=None, end=None):
        points = (await self.forecast(loc)).hourly
        return [point for point in points if (start is None or point.time >= start) and (end is None or point.time <= end)]
    async def get_daily(self, loc: Location, start=None, end=None):
        from .decision import daily_summary
        return daily_summary([point.model_dump(mode='json') for point in await self.get_hourly(loc, start, end)], loc.timezone)
    async def get_alerts(self, loc: Location): return []
    async def get_historical(self, *args, **kwargs):
        raise NotImplementedError(f'{self.id} does not provide historical data through this adapter')
    async def json(self, url, params):
        for attempt in range(2):
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt: raise
                await asyncio.sleep(.25)

Provider = WeatherProvider

class OpenMeteo(WeatherProvider):
    id = 'open-meteo'
    display_name = 'Open-Meteo'
    model_family = 'gfs'
    async def forecast(self, loc: Location):
        data = await self.json('https://api.open-meteo.com/v1/forecast', {
            'latitude':loc.latitude, 'longitude':loc.longitude, 'timezone':'UTC',
            'models':'gfs_seamless', 'forecast_days':7, 'wind_speed_unit':'ms',
            'hourly':'temperature_2m,apparent_temperature,precipitation_probability,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m,visibility,pressure_msl,cloud_cover,uv_index,weather_code'})
        h = data['hourly']
        return Forecast(provider=self.id, model_family='gfs', hourly=[Point(
            time=datetime.fromisoformat(t).replace(tzinfo=timezone.utc),
            temperature=h['temperature_2m'][i], rain_chance=h['precipitation_probability'][i],
            rain_mm=h['precipitation'][i], wind_ms=h['wind_speed_10m'][i],
            humidity=h['relative_humidity_2m'][i], apparent_temperature=h['apparent_temperature'][i],
            wind_direction=h['wind_direction_10m'][i], wind_gust_ms=h['wind_gusts_10m'][i],
            visibility_m=h['visibility'][i], pressure_hpa=h['pressure_msl'][i],
            cloud_cover=h['cloud_cover'][i], uv_index=h['uv_index'][i],
            weather_code=h['weather_code'][i]) for i,t in enumerate(h['time'])])

class OpenWeather(WeatherProvider):
    id = 'openweather'
    display_name = 'OpenWeather'
    model_family = 'openweather-unknown'
    @property
    def enabled(self): return bool(self.settings.openweather_api_key)
    async def forecast(self, loc):
        data = await self.json('https://api.openweathermap.org/data/2.5/forecast', {
            'lat':loc.latitude, 'lon':loc.longitude, 'appid':self.settings.openweather_api_key, 'units':'metric'})
        # Three-hour precipitation is NOT mixed with one-hour rainfall totals.
        return Forecast(provider=self.id, model_family='openweather-unknown', hourly=[Point(
            time=datetime.fromtimestamp(v['dt'], timezone.utc), temperature=v['main']['temp'],
            apparent_temperature=v['main'].get('feels_like'), wind_ms=v['wind']['speed'],
            wind_direction=v['wind'].get('deg'), wind_gust_ms=v['wind'].get('gust'),
            humidity=v['main']['humidity'], pressure_hpa=v['main'].get('pressure'),
            visibility_m=v.get('visibility'), cloud_cover=v.get('clouds',{}).get('all'),
            weather_code=v.get('weather',[{}])[0].get('id')) for v in data['list']])

class WeatherApi(WeatherProvider):
    id = 'weatherapi'
    display_name = 'WeatherAPI'
    model_family = 'weatherapi-unknown'
    @property
    def enabled(self): return bool(self.settings.weatherapi_key)
    async def forecast(self, loc):
        data = await self.json('https://api.weatherapi.com/v1/forecast.json', {
            'key':self.settings.weatherapi_key, 'q':f'{loc.latitude},{loc.longitude}', 'days':3})
        return Forecast(provider=self.id, model_family='weatherapi-unknown', hourly=[Point(
            time=datetime.fromtimestamp(v['time_epoch'], timezone.utc), temperature=v['temp_c'],
            rain_chance=v.get('chance_of_rain'), rain_mm=v.get('precip_mm'),
            wind_ms=v['wind_kph']/3.6, wind_direction=v.get('wind_degree'),
            wind_gust_ms=v.get('gust_kph',0)/3.6, humidity=v.get('humidity'),
            apparent_temperature=v.get('feelslike_c'), visibility_m=v.get('vis_km',0)*1000,
            pressure_hpa=v.get('pressure_mb'), cloud_cover=v.get('cloud'), uv_index=v.get('uv'))
            for d in data['forecast']['forecastday'] for v in d['hour']])

class Imd(WeatherProvider):
    id = 'imd'
    display_name = 'India Meteorological Department'
    model_family = 'imd-station'
    @property
    def enabled(self): return self.settings.imd_enabled
    async def forecast(self, loc):
        # Station mapping must be verified before attaching station data to a village.
        # Retain a real access probe, but never coerce daily min/max into hourly values.
        data = await self.json('https://api.imd.gov.in/api/v1/cityforecastloc', {})
        if not isinstance(data, list): raise ValueError('IMD access or schema unavailable')
        raise ValueError('IMD station mapping and daily schema integration pending')

PROVIDERS = [OpenMeteo, OpenWeather, WeatherApi, Imd]
