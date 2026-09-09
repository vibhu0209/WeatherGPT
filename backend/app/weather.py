import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import median
import httpx
import math
import time
import logging
import yaml
from .models import Settings, Location, Forecast
from .providers import PROVIDERS
from .decision import ALL_PROFILES, current_point, daily_summary, recommendations, weather_score
from .risks import estimate_risks

audit_log = logging.getLogger('weathergpt.weather')
_WEIGHTS_PATH = Path(__file__).resolve().parent / 'config' / 'provider_weights.yaml'


def load_provider_weights() -> dict:
    if not _WEIGHTS_PATH.exists():
        return {'defaults': {}, 'variables': {}}
    with _WEIGHTS_PATH.open(encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {'defaults': {}, 'variables': {}}


def provider_weight(provider: str, field: str | None = None, weights: dict | None = None) -> float:
    config = load_provider_weights() if weights is None else weights
    if field:
        variable_weights = (config.get('variables') or {}).get(field) or {}
        if provider in variable_weights:
            value = float(variable_weights[provider])
            return value if math.isfinite(value) and value > 0 else 1.0
    value = float((config.get('defaults') or {}).get(provider, 1.0))
    return value if math.isfinite(value) and value > 0 else 1.0


def weighted_median(values: list[tuple[float, float]]) -> float | None:
    if not values:
        return None
    ordered = sorted(values, key=lambda item: item[0])
    total = sum(weight for _, weight in ordered)
    midpoint = total / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= midpoint:
            return round(value, 1)
    return round(ordered[-1][0], 1)

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
            audit_log.info('weather_cache_hit source_count=%s', cached.get('source_count', 0))
            return {**cached, 'location':loc.model_dump()}
        audit_log.info('weather_cache_miss')
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
                audit_log.warning('weather_all_providers_unavailable stale_fallback=%s', bool(cached))
                if cached:
                    return {**cached, 'location':loc.model_dump(), 'is_stale':True, 'provider_status':[s for r,s in results]}
                return {'location':loc.model_dump(), 'hourly':[], 'retrieved_at':now.isoformat(),
                    'is_stale':False, 'sources':[], 'source_count':0, 'agreement':'unavailable',
                    'provider_status':[s for r,s in results], 'alerts_status':'unavailable', 'alerts':[]}
            hourly, disagreement, disagreement_reasons = fuse(forecasts, now)
            confidence = confidence_for(hourly, forecasts, disagreement_reasons)
            audit_log.info('weather_fusion source_count=%s hourly_points=%s disagreement=%s',
                len(forecasts), len(hourly), bool(disagreement_reasons))
            result = {'location':loc.model_dump(), 'hourly':hourly, 'retrieved_at':now.isoformat(),
                'is_stale':False, 'sources':[f.provider for f in forecasts], 'source_count':len(forecasts),
                'agreement':'sources_disagree' if disagreement else ('single_source' if len(forecasts)==1 else 'multi_source_consensus'),
                'confidence':confidence, 'disagreement_reasons':disagreement_reasons,
                'provider_status':[s for r,s in results], 'alerts_status':'unavailable', 'alerts':[]}
            result['current'] = current_point(hourly)
            result['daily'] = daily_summary(hourly, loc.timezone)
            result['scores'] = {profile: weather_score(hourly, profile) for profile in ALL_PROFILES}
            result['recommendations'] = {profile: recommendations(hourly, profile) for profile in ALL_PROFILES}
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


def weighted_circular_mean(values: list[tuple[float, float]]) -> float | None:
    if not values:
        return None
    x = sum(math.cos(math.radians(value)) * weight for value, weight in values)
    y = sum(math.sin(math.radians(value)) * weight for value, weight in values)
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return round(math.degrees(math.atan2(y, x)) % 360, 1)


def weighted_vote(values: list[tuple[float, float]]) -> float | None:
    totals: dict[float, float] = {}
    for value, weight in values:
        totals[value] = totals.get(value, 0.0) + weight
    if not totals:
        return None
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return ordered[0][0] if len(ordered) == 1 or ordered[0][1] > ordered[1][1] else None


def fuse(forecasts: list[Forecast], now: datetime):
    weights_config = load_provider_weights()
    buckets = {}
    families = set()
    for forecast in forecasts:
        if forecast.model_family in families: continue
        if abs((now-forecast.retrieved_at).total_seconds()) > 3600: continue
        families.add(forecast.model_family)
        for p in forecast.hourly:
            if now-timedelta(hours=1) <= p.time <= now+timedelta(days=7):
                buckets.setdefault(p.time.isoformat(), []).append((forecast.provider, p))
    output, reasons = [], set()
    for t, points in sorted(buckets.items()):
        row = {'time':t, 'source_count':len(points)}
        for field in ['temperature','apparent_temperature','rain_chance','rain_mm','wind_ms','wind_gust_ms','humidity','visibility_m','pressure_hpa','cloud_cover','uv_index']:
            weighted_values = [(getattr(point, field), provider_weight(provider, field, weights_config))
                for provider, point in points if getattr(point, field) is not None]
            values = [value for value, _ in weighted_values]
            row[field] = weighted_median(weighted_values)
            row[f'{field}_source_count'] = len(values)
            if field=='temperature' and values and max(values)-min(values)>5: reasons.add('temperature spread exceeds 5°C')
            if field=='rain_chance' and values and max(values)-min(values)>40: reasons.add('rain chance spread exceeds 40 percentage points')
            if field=='wind_ms' and values and max(values)-min(values)>8: reasons.add('wind speed spread exceeds 8 m/s')
        directions = [(point.wind_direction, provider_weight(provider, 'wind_direction', weights_config))
            for provider, point in points if point.wind_direction is not None]
        row['wind_direction'] = weighted_circular_mean(directions)
        row['wind_direction_source_count'] = len(directions)
        codes = [(point.weather_code, provider_weight(provider, 'weather_code', weights_config))
            for provider, point in points if point.weather_code is not None]
        row['weather_code'] = weighted_vote(codes)
        row['weather_code_source_count'] = len(codes)
        if len({value for value, _ in codes}) > 1: reasons.add('weather condition categories disagree')
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
