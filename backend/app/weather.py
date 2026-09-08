import asyncio
from datetime import datetime, timezone, timedelta
from statistics import median
import httpx
import math
import time
from .models import Settings, Location, Forecast
from .providers import PROVIDERS
from .decision import current_point, daily_summary, recommendations, weather_score
from .risks import estimate_risks

class WeatherService:
    def __init__(self):
        self.settings = Settings()
        self.cache = {}
        self.failures = {}
        self.lock = asyncio.Lock()

    async def bundle(self, loc: Location):
        key = (loc.latitude, loc.longitude, loc.timezone)
        now = datetime.now(timezone.utc)
        cached = self.cache.get(key)
        if cached and (now - datetime.fromisoformat(cached['retrieved_at'])).total_seconds() < 900:
            return {**cached, 'location':loc.model_dump()}
        async with self.lock:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                providers = [p(client, self.settings) for p in PROVIDERS]
                async def fetch(p):
                    if not p.enabled: return None, {'provider':p.id, 'status':'not_configured'}
                    if self.failures.get(p.id, now) > now:
                        return None, {'provider':p.id, 'status':'temporarily_unavailable'}
                    started = time.monotonic()
                    try:
                        result = await asyncio.wait_for(p.forecast(loc), 14)
                        return result, {'provider':p.id, 'status':'available', 'latency_ms':round((time.monotonic()-started)*1000,1)}
                    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, TimeoutError):
                        self.failures[p.id] = now + timedelta(seconds=60)
                        return None, {'provider':p.id, 'status':'unavailable', 'latency_ms':round((time.monotonic()-started)*1000,1)}
                results = await asyncio.gather(*(fetch(p) for p in providers))
            forecasts = [r for r,s in results if r]
            if not forecasts:
                if cached:
                    return {**cached, 'location':loc.model_dump(), 'is_stale':True, 'provider_status':[s for r,s in results]}
                return {'location':loc.model_dump(), 'hourly':[], 'retrieved_at':now.isoformat(),
                    'is_stale':False, 'sources':[], 'source_count':0, 'agreement':'unavailable',
                    'provider_status':[s for r,s in results], 'alerts_status':'unavailable', 'alerts':[]}
            hourly, disagreement, disagreement_reasons = fuse(forecasts, now)
            confidence = confidence_for(hourly, forecasts, disagreement_reasons)
            result = {'location':loc.model_dump(), 'hourly':hourly, 'retrieved_at':now.isoformat(),
                'is_stale':False, 'sources':[f.provider for f in forecasts], 'source_count':len(forecasts),
                'agreement':'sources_disagree' if disagreement else ('single_source' if len(forecasts)==1 else 'multi_source_consensus'),
                'confidence':confidence, 'disagreement_reasons':disagreement_reasons,
                'provider_status':[s for r,s in results], 'alerts_status':'unavailable', 'alerts':[]}
            result['current'] = current_point(hourly)
            result['daily'] = daily_summary(hourly, loc.timezone)
            result['scores'] = {profile: weather_score(hourly, profile) for profile in ('general', 'farming', 'fishing', 'outdoor')}
            result['recommendations'] = {profile: recommendations(hourly, profile) for profile in ('general', 'farming', 'fishing', 'outdoor')}
            result['risk_estimates'] = estimate_risks(hourly)
            if len(self.cache) >= 256: self.cache.pop(next(iter(self.cache)))
            self.cache[key] = result
            return result

def circular_mean(values: list[float]) -> float | None:
    if not values:
        return None
    radians = [math.radians(value) for value in values]
    x = sum(math.cos(value) for value in radians)
    y = sum(math.sin(value) for value in radians)
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return round(math.degrees(math.atan2(y, x)) % 360, 1)


def fuse(forecasts: list[Forecast], now: datetime):
    buckets = {}
    families = set()
    for forecast in forecasts:
        if forecast.model_family in families: continue
        if abs((now-forecast.retrieved_at).total_seconds()) > 3600: continue
        families.add(forecast.model_family)
        for p in forecast.hourly:
            if now-timedelta(hours=1) <= p.time <= now+timedelta(days=7):
                buckets.setdefault(p.time.isoformat(), []).append(p)
    output, reasons = [], set()
    for t, points in sorted(buckets.items()):
        row = {'time':t, 'source_count':len(points)}
        for field in ['temperature','apparent_temperature','rain_chance','rain_mm','wind_ms','wind_gust_ms','humidity','visibility_m','pressure_hpa','cloud_cover','uv_index','weather_code']:
            values = [getattr(p,field) for p in points if getattr(p,field) is not None]
            row[field] = round(median(values),1) if values else None
            row[f'{field}_source_count'] = len(values)
            if field=='temperature' and values and max(values)-min(values)>5: reasons.add('temperature spread exceeds 5°C')
            if field=='rain_chance' and values and max(values)-min(values)>40: reasons.add('rain chance spread exceeds 40 percentage points')
            if field=='wind_ms' and values and max(values)-min(values)>8: reasons.add('wind speed spread exceeds 8 m/s')
        directions = [p.wind_direction for p in points if p.wind_direction is not None]
        row['wind_direction'] = circular_mean(directions)
        row['wind_direction_source_count'] = len(directions)
        output.append(row)
    return output, bool(reasons), sorted(reasons)


def confidence_for(hourly: list[dict], forecasts: list[Forecast], reasons: list[str]) -> dict:
    independent_models = len({forecast.model_family for forecast in forecasts})
    coverage = 0 if not hourly else sum(1 for point in hourly[:24] if point.get('temperature') is not None and point.get('wind_ms') is not None) / min(24, len(hourly))
    score = min(90, 35 + independent_models * 15 + round(coverage * 25))
    score -= min(30, len(reasons) * 12)
    score = max(0, score)
    label = 'High agreement' if score >= 75 else 'Moderate agreement' if score >= 50 else 'Low agreement'
    explanation = [f'{independent_models} independent model source(s)', f'{coverage * 100:.0f}% core-variable coverage']
    explanation.extend(reasons)
    return {'score':score,'label':label,'calibrated_probability':False,'reasons':explanation}

service = WeatherService()
