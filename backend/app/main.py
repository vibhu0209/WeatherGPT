from datetime import datetime, timezone
import json
import hashlib
import math
import logging
import os
import uuid
import asyncio
import httpx
from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from .models import Location, ChatRequest, Settings
from .weather import service
from .chat import answer
from .chat_tools import run_chat
from .ai import validate_translation
from .decision import current_point, daily_summary, weather_score, apply_official_warning_limit, recommendations
from .climate import climate_service
from .risks import estimate_risks
from .metrics import metrics
from .alerts import alert_service
from .marine import marine_service
from .groq_client import groq_client
from .delivery import delivery_chain
from .language import language_service, BhashiniProvider, GoogleTranslationProvider
from .subscriptions import (
    authenticate as authenticate_device,
    create as create_subscription,
    delete as delete_subscription,
    list_for_device,
    register as register_device_record,
    revoke as revoke_device,
)
from .cache import RedisRateLimitBackend
from .security import SlidingWindowLimiter, public_location, finite_coordinate
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title='WeatherGPT', version='0.1.0')
app.add_middleware(GZipMiddleware, minimum_size=1000)
_settings = Settings()
_cors_origins = [origin.strip() for origin in (_settings.cors_origins or '').split(',') if origin.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=['GET', 'POST', 'DELETE'],
        allow_headers=['Authorization', 'Content-Type', 'X-Request-Id', 'X-Device-Id', 'If-None-Match'],
        expose_headers=['ETag', 'X-Request-Id'],
        max_age=600,
    )
def build_rate_limiter():
    if _settings.redis_url:
        try:
            return RedisRateLimitBackend(_settings.redis_url, 90, 60)
        except Exception:
            pass
    return SlidingWindowLimiter(limit=90, window_seconds=60, max_keys=4096)


rate_limiter = build_rate_limiter()
register_limiter = SlidingWindowLimiter(limit=10, window_seconds=60, max_keys=4096)


def configure_logging(level: str | None = None) -> None:
    """Attach a stream handler to the weathergpt loggers.

    Uvicorn configures only its own loggers, so without this the request,
    provider-latency, cache and fusion records are dropped at WARNING and the
    service runs with no observability. Records stay propagating so pytest's
    caplog and any parent handlers still see them.
    """
    resolved = (level or os.getenv('LOG_LEVEL') or 'INFO').upper()
    logger = logging.getLogger('weathergpt')
    logger.setLevel(getattr(logging, resolved, logging.INFO))
    if not any(getattr(handler, 'name', '') == 'weathergpt' for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.name = 'weathergpt'
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        logger.addHandler(handler)


configure_logging()
audit_log = logging.getLogger('weathergpt.request')


def error_response(request: Request | None, code: str, message: str, retryable: bool, status: int):
    request_id = getattr(getattr(request, 'state', None), 'request_id', None)
    return JSONResponse({'code': code, 'message': message, 'retryable': retryable, 'request_id': request_id}, status)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    return JSONResponse({'code': 'validation_error', 'message': 'Please check the information and try again.',
        'retryable': False, 'request_id': getattr(request.state, 'request_id', None),
        'details': [{'field': '.'.join(str(part) for part in item['loc'][1:]), 'message': item['msg']} for item in error.errors()]}, 422)


@app.exception_handler(404)
async def not_found(request: Request, _error):
    return error_response(request, 'not_found', 'That resource was not found.', False, 404)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    audit_log.exception('unhandled_error request_id=%s path=%s', getattr(request.state, 'request_id', None), request.url.path)
    return error_response(request, 'internal_error', 'Something went wrong. Please try again.', True, 500)


@app.middleware('http')
async def limits(request: Request, call_next):
    started = __import__('time').monotonic()
    supplied = request.headers.get('x-request-id', '')
    request_id = supplied if 0 < len(supplied) <= 80 and supplied.replace('-', '').isalnum() else str(uuid.uuid4())
    request.state.request_id = request_id
    ip = request.client.host if request.client else 'unknown'
    health_path = request.url.path in {'/health', '/ready'}
    if not health_path and not rate_limiter.allow(ip):
        response = JSONResponse({'code': 'rate_limited', 'message': 'Please wait a minute and try again.', 'retryable': True, 'request_id': request_id}, 429)
        response.headers['x-request-id'] = request_id
        return response
    if request.method == 'POST':
        body = await request.body()
        if len(body) > 16384:
            response = JSONResponse({'code': 'too_large', 'message': 'Please send a shorter message.', 'retryable': False, 'request_id': request_id}, 413)
            response.headers['x-request-id'] = request_id
            return response
    try:
        response = await call_next(request)
    except Exception:
        audit_log.exception('unhandled_error request_id=%s path=%s', request_id, request.url.path)
        response = error_response(request, 'internal_error', 'Something went wrong. Please try again.', True, 500)
    response.headers['x-request-id'] = request_id
    response.headers.setdefault('x-content-type-options', 'nosniff')
    response.headers.setdefault('x-frame-options', 'DENY')
    response.headers.setdefault('referrer-policy', 'no-referrer')
    response.headers.setdefault('permissions-policy', 'geolocation=(), microphone=(), camera=()')
    audit_log.info(json.dumps({'event': 'http_request', 'request_id': request_id, 'method': request.method,
        'path': request.url.path, 'status': response.status_code,
        'duration_ms': round((__import__('time').monotonic() - started) * 1000, 1)}, separators=(',', ':')))
    return response


@app.get('/health')
def health():
    return {'status': 'ok', 'time': datetime.now(timezone.utc).isoformat()}


@app.get('/ready')
def ready():
    from .locations import google_places_configured, google_places_enabled
    return {
        'status': 'ready',
        'cache': type(service.cache).__name__.replace('CacheBackend', '').lower(),
        'store': __import__('os').getenv('WEATHERGPT_STORE') or service.settings.store_backend or 'memory',
        'groq': groq_client.enabled,
        'gemini': False,
        'google_places_configured': google_places_configured(service.settings),
        'google_places_enabled': google_places_enabled(service.settings),
        'cap_alerts': bool(service.settings.cap_alert_url),
        'performance': metrics.snapshot(),
        'time': datetime.now(timezone.utc).isoformat(),
    }


@app.get('/v1/capabilities')
def capabilities():
    settings = service.settings
    from .locations import google_places_configured, google_places_enabled
    live_translation = bool(
        (settings.bhashini_compute_url and settings.bhashini_api_key and settings.bhashini_user_id and settings.bhashini_translation_service_id)
        or settings.google_translate_api_key
    )
    return {
        'forecast': True, 'chat': 'groq_tool_orchestrated' if groq_client.enabled else 'deterministic_fallback', 'official_alerts': bool(settings.cap_alert_url), 'marine': True,
        'climate': True, 'cloud_voice': False, 'groq': groq_client.enabled, 'gemini': False, 'demo_mode': False,
        'answer_languages': ['en', 'hi', 'bn', 'te', 'mr', 'ta', 'gu', 'kn', 'ml', 'pa', 'or'],
        'live_translation': live_translation,
        'google_places_configured': google_places_configured(settings),
        'google_places_enabled': google_places_enabled(settings),
        'alert_delivery': [{'transport': provider.transport, 'status': 'disabled'} for provider in delivery_chain],
    }


@app.get('/v1/languages/capabilities')
def language_capabilities():
    settings = service.settings
    providers = [BhashiniProvider(None, settings), GoogleTranslationProvider(None, settings)]
    live = any(provider.enabled for provider in providers)
    return {
        'ui_languages': ['en', 'hi', 'bn', 'te', 'mr', 'ta', 'gu', 'kn', 'ml', 'pa', 'or'],
        'answer_languages': ['en', 'hi', 'bn', 'te', 'mr', 'ta', 'gu', 'kn', 'ml', 'pa', 'or'],
        'answer_mode': 'deterministic_templates',
        'live_translation': live,
        'providers': [provider.health() for provider in providers],
        'fallback': {
            'translation': 'deterministic templates in the selected language; original text if a live translator fails',
            'asr': 'Android installed recognizer',
            'tts': 'Android installed TTS',
        },
        'cloud_voice': False,
    }


async def finalize_chat(request: ChatRequest, result: dict):
    origin = result.get('response_origin') or ''
    # Groq-orchestrated answers are already natural-language and validator-checked.
    # Deterministic answers stay as drafted — no second LLM polish pass (saves tokens).
    if origin != 'groq_tool_orchestrated':
        result.setdefault('response_origin', 'deterministic_fallback')
    if not result.get('follow_up_suggestions'):
        from .groq_orchestrator import _follow_ups_for
        tools = result.get('used_tools') or ([result['tool']] if result.get('tool') else [])
        result['follow_up_suggestions'] = _follow_ups_for(request, [t for t in tools if t])
    target = request.language
    current = result.get('language', 'en')
    if target != current:
        translated = await language_service.translate(result['answer'], current if current in ('en', 'hi') else 'en', target)
        if not translated['fallback'] and validate_translation(result['answer'], translated['text']):
            result['answer'] = translated['text']
            result['language'] = target
            result['language_provider'] = translated['provider']
        else:
            result['language_provider'] = 'deterministic' if current == target else 'original'
            if current != target and current in ('en', 'hi'):
                result['language'] = current
    else:
        result['language_provider'] = result.get('language_provider') or (
            'groq' if origin == 'groq_tool_orchestrated' else 'deterministic'
        )
    if 'conversation_context' in result and 'resolved_location' in result['conversation_context']:
        result['conversation_context']['resolved_location'] = public_location(request.location)
    return result


@app.get('/v1/providers/status')
def providers():
    return {'providers': [p(None, service.settings).health() for p in __import__('app.providers', fromlist=['PROVIDERS']).PROVIDERS]}


@app.get('/v1/locations/search')
async def search(request: Request, q: str = Query(min_length=2, max_length=100), language: str = Query(default='en', pattern='^(en|hi|bn|te|mr|ta|gu|kn|ml|pa|or)$')):
    from .locations import search_places_with_meta
    try:
        places, meta = await search_places_with_meta(q, language, _settings)
        return {
            'locations': [place.model_dump() for place in places],
            'provider': meta.provider,
            'fallback_used': meta.fallback_used,
            'cached': meta.cached,
            'result_count': meta.result_count,
            'latency_ms': meta.latency_ms,
        }
    except Exception:
        return error_response(request, 'unavailable', 'Place search is unavailable. Please try again.', True, 503)


class LocationBody(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str = Field(default='Current location', min_length=1, max_length=120)
    @field_validator('latitude')
    @classmethod
    def finite_lat(cls, value):
        return finite_coordinate(value, -90, 90)
    @field_validator('longitude')
    @classmethod
    def finite_lon(cls, value):
        return finite_coordinate(value, -180, 180)


class BundleBody(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str = Field(default='Selected place', min_length=1, max_length=120)
    timezone: str = Field(default='Asia/Kolkata', max_length=64)
    hours: int = Field(default=168, ge=24, le=168)
    @field_validator('latitude')
    @classmethod
    def finite_lat(cls, value):
        return finite_coordinate(value, -90, 90)
    @field_validator('longitude')
    @classmethod
    def finite_lon(cls, value):
        return finite_coordinate(value, -180, 180)


async def _resolve_location(request: Request, latitude: float, longitude: float, name: str):
    from .locations import resolve_timezone
    try:
        location = await resolve_timezone(latitude, longitude, name, _settings)
        return {'location': location.model_dump()}
    except Exception:
        return error_response(request, 'location_unavailable', 'The location could not be checked. Please search for your village or city.', True, 503)


@app.get('/v1/locations/resolve')
async def resolve_location(request: Request, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = Query(default='Current location', max_length=120)):
    return await _resolve_location(request, latitude, longitude, name)


@app.post('/v1/locations/resolve')
async def resolve_location_post(request: Request, body: LocationBody):
    return await _resolve_location(request, body.latitude, body.longitude, body.name)


ADVICE_ETAG_REVISION = '2'


def bundle_etag(data: dict, official: dict, hours: int) -> str:
    alert_ids = ','.join(sorted(str(alert.get('id') or '') for alert in official.get('alerts') or []))
    material = '|'.join([
        str(data.get('retrieved_at') or ''),
        str(bool(data.get('is_stale'))),
        str(data.get('source_count') or 0),
        str(data.get('agreement') or ''),
        str(official.get('status') or ''),
        alert_ids,
        str(hours),
        ADVICE_ETAG_REVISION,
    ])
    return '"' + hashlib.sha256(material.encode()).hexdigest() + '"'


async def _weather_bundle(request: Request, response: Response, latitude: float, longitude: float, name: str, timezone_name: str, hours: int):
    try:
        loc = Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone_name)
    except ValueError:
        return error_response(request, 'invalid_location', 'Please check the location and timezone.', False, 422)
    data, official = await asyncio.gather(service.bundle(loc), alert_service.official(loc))
    etag = bundle_etag(data, official, hours)
    headers = {'etag': etag, 'cache-control': 'private, max-age=300'}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304, headers=headers)
    scores = {
        profile: apply_official_warning_limit(score, official['alerts'])
        for profile, score in (data.get('scores') or {}).items()
    }
    marine_hourly = ((data.get('marine') or {}).get('hourly') or [])
    advice = {
        profile: recommendations(
            data.get('hourly') or [], profile,
            marine_hourly if profile == 'fishing' else None,
            timezone_name=loc.timezone, official_alerts=official['alerts'],
            official_status=official['status'], agreement=data.get('agreement'),
            confidence=data.get('confidence'), is_stale=bool(data.get('is_stale')),
            sources=data.get('sources'), marine_available=(data.get('marine') or {}).get('available'),
        )
        for profile in (data.get('scores') or {})
    }
    payload = {**data, 'hourly': data.get('hourly', [])[:hours], 'daily': data.get('daily', [])[:math.ceil(hours / 24)],
        'scores': scores, 'recommendations': advice,
        'alerts_status': official['status'], 'official_status': official['status'],
        'alerts': official['alerts'], 'official_alerts': official['alerts'], 'alerts_message': official['message']}
    response.headers.update(headers)
    return payload


@app.get('/v1/weather/bundle')
async def bundle(request: Request, response: Response, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = Query(default='Selected place', max_length=120), timezone: str = 'Asia/Kolkata', hours: int = Query(default=168, ge=24, le=168)):
    return await _weather_bundle(request, response, latitude, longitude, name, timezone, hours)


@app.post('/v1/weather/bundle')
async def bundle_post(request: Request, response: Response, body: BundleBody):
    return await _weather_bundle(request, response, body.latitude, body.longitude, body.name, body.timezone, body.hours)


async def weather_for(latitude: float, longitude: float, name: str, timezone_name: str):
    return await service.bundle(Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone_name))


@app.get('/v1/weather/current')
async def current(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected place', timezone: str = 'Asia/Kolkata'):
    data = await weather_for(latitude, longitude, name, timezone)
    return {key: data[key] for key in ('location', 'retrieved_at', 'is_stale', 'sources', 'source_count', 'agreement', 'provider_status')} | {'data': data.get('current') or current_point(data['hourly'])}


@app.get('/v1/weather/hourly')
async def hourly(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected place', timezone: str = 'Asia/Kolkata', hours: int = Query(default=24, ge=1, le=168)):
    data = await weather_for(latitude, longitude, name, timezone)
    return {key: data[key] for key in ('location', 'retrieved_at', 'is_stale', 'sources', 'source_count', 'agreement', 'provider_status')} | {'data': data['hourly'][:hours]}


@app.get('/v1/weather/daily')
async def daily(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected place', timezone: str = 'Asia/Kolkata', days: int = Query(default=7, ge=1, le=7)):
    data = await weather_for(latitude, longitude, name, timezone)
    summaries = data.get('daily') or daily_summary(data['hourly'], timezone)
    return {key: data[key] for key in ('location', 'retrieved_at', 'is_stale', 'sources', 'source_count', 'agreement', 'provider_status')} | {'data': summaries[:days]}


PROFILE_PATTERN = '^(general|farming|fishing|outdoor|tourism|transport|construction|emergency|vendor|aviation|research)$'


@app.get('/v1/weather/score')
async def score(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected place', timezone: str = 'Asia/Kolkata', profile: str = Query(default='general', pattern=PROFILE_PATTERN)):
    data = await weather_for(latitude, longitude, name, timezone)
    return {'location': data['location'], 'retrieved_at': data['retrieved_at'], 'is_stale': data['is_stale'], 'data': data.get('scores', {}).get(profile) or weather_score(data['hourly'], profile), 'recommendations': data.get('recommendations', {}).get(profile, [])}


@app.get('/v1/weather/alerts')
async def alerts(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected place', timezone: str = 'Asia/Kolkata'):
    data = await weather_for(latitude, longitude, name, timezone)
    official = await alert_service.official(Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone))
    return {
        'location': data['location'],
        'status': official['status'],
        'official_status': official['status'],
        'alerts': official['alerts'],
        'official_alerts': official['alerts'],
        'risk_estimates': data.get('risk_estimates') or estimate_risks(data['hourly']),
        'retrieved_at': data['retrieved_at'],
        'is_stale': data['is_stale'],
        'message': official['message'],
    }


@app.get('/v1/hazards/infrastructure')
async def infrastructure_hazard(
    request: Request,
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    name: str = 'Selected place',
    timezone: str = 'Asia/Kolkata',
):
    """Landslide / road-connectivity risk estimate for emergency dashboards (not official)."""
    from .geohazard import assess_infrastructure_hazard
    location = Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone)
    try:
        data = await weather_for(latitude, longitude, name, timezone)
        official = await alert_service.official(location)
        hazard = await assess_infrastructure_hazard(location, data.get('hourly') or [], official.get('alerts') or [])
        return {'location': data['location'], 'data': hazard, 'is_stale': data.get('is_stale', False)}
    except httpx.HTTPError:
        return error_response(request, 'hazard_unavailable', 'Infrastructure hazard inputs could not be checked right now.', True, 503)


@app.get('/v1/climate/summary')
async def climate_summary(request: Request, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected place', timezone: str = 'Asia/Kolkata', metric: str = Query(default='temperature', pattern='^(temperature|rainfall)$'), years: int = Query(default=10, ge=2, le=30)):
    try:
        data = await climate_service.summary(Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone), metric, years)
        return {'data': data, 'is_stale': False}
    except httpx.HTTPError:
        return error_response(request, 'climate_unavailable', 'Historical climate data is unavailable. Please try again later.', True, 503)
    except ValueError:
        return error_response(request, 'insufficient_climate_data', 'Not enough complete historical years for a reliable trend.', False, 422)


@app.get('/v1/marine/forecast')
async def marine_forecast(request: Request, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected sea point', timezone: str = 'Asia/Kolkata', hours: int = Query(default=48, ge=1, le=168)):
    try:
        return await marine_service.forecast(Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone), hours)
    except httpx.HTTPError:
        return error_response(request, 'marine_unavailable', 'Marine forecast data could not be checked. Check official IMD and INCOIS warnings.', True, 503)
    except ValueError:
        return error_response(request, 'marine_location_unavailable', 'Marine forecast is unavailable for that location.', False, 422)


@app.get('/v1/weather/marine')
async def weather_marine_alias(request: Request, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = 'Selected sea point', timezone: str = 'Asia/Kolkata', hours: int = Query(default=48, ge=1, le=168)):
    return await marine_forecast(request, latitude, longitude, name, timezone, hours)


class TranslateBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    source: str = Field(default='en', pattern='^(en|hi|bn|te|mr|ta|gu|kn|ml|pa|or)$')
    target: str = Field(pattern='^(en|hi|bn|te|mr|ta|gu|kn|ml|pa|or)$')


@app.post('/v1/translate')
async def translate(request: Request, body: TranslateBody):
    result = await language_service.translate(body.text, body.source, body.target)
    return {'text': result['text'], 'provider': result['provider'], 'fallback': result['fallback'],
            'source': body.source, 'target': body.target}


@app.post('/v1/voice/transcribe')
async def voice_transcribe(request: Request):
    return error_response(request, 'voice_unavailable', 'Cloud voice transcription is not configured. Use on-device Android speech recognition.', False, 501)


@app.post('/v1/voice/synthesize')
async def voice_synthesize(request: Request):
    return error_response(request, 'voice_unavailable', 'Cloud voice synthesis is not configured. Use on-device Android text-to-speech.', False, 501)


@app.post('/v1/chat/message')
async def chat(request: ChatRequest):
    return await finalize_chat(request, await run_chat(request))


class DeviceRegistration(BaseModel):
    device_id: str | None = Field(default=None, min_length=8, max_length=80)


class AlertSubscriptionRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(default='Asia/Kolkata', max_length=64)
    channels: list[str] = Field(default_factory=lambda: ['severe'])
    @field_validator('latitude')
    @classmethod
    def finite_lat(cls, value):
        return finite_coordinate(value, -90, 90)
    @field_validator('longitude')
    @classmethod
    def finite_lon(cls, value):
        return finite_coordinate(value, -180, 180)


@app.post('/v1/device/register')
def register_device(request: Request, body: DeviceRegistration | None = None):
    ip = request.client.host if request.client else 'unknown'
    if not register_limiter.allow(ip):
        return error_response(request, 'rate_limited', 'Please wait a minute and try again.', True, 429)
    try:
        return register_device_record(body.device_id if body else None)
    except PermissionError:
        return error_response(request, 'device_id_taken', 'That device id is already registered. Register without a device id to get a new one.', False, 409)
    except ValueError:
        return error_response(request, 'invalid_device_id', 'The device id is not valid.', False, 422)


@app.post('/v1/device/revoke')
def revoke_registered_device(request: Request, x_device_id: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    try:
        device = authenticate_device(x_device_id, authorization)
    except PermissionError:
        return error_response(request, 'unauthorized', 'Device authentication required.', False, 401)
    revoke_device(device.device_id)
    return {'revoked': True, 'device_id': device.device_id}


@app.post('/v1/alerts/subscriptions')
def create_alert_subscription(request: Request, body: AlertSubscriptionRequest, x_device_id: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    try:
        device = authenticate_device(x_device_id, authorization)
    except PermissionError:
        return error_response(request, 'unauthorized', 'Device authentication required.', False, 401)
    try:
        subscription = create_subscription(device.device_id, body.latitude, body.longitude, body.timezone, body.channels)
    except ValueError:
        return error_response(request, 'subscription_limit', 'This device already has the maximum number of alert subscriptions.', False, 409)
    return {'subscription': {
        'id': subscription.id,
        'device_id': subscription.device_id,
        'latitude': subscription.latitude,
        'longitude': subscription.longitude,
        'timezone': subscription.timezone,
        'channels': subscription.channels,
        'created_at': subscription.created_at,
    }}


@app.get('/v1/alerts/subscriptions')
def list_alert_subscriptions(request: Request, x_device_id: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    try:
        device = authenticate_device(x_device_id, authorization)
    except PermissionError:
        return error_response(request, 'unauthorized', 'Device authentication required.', False, 401)
    return {'subscriptions': [{
        'id': item.id,
        'device_id': item.device_id,
        'latitude': item.latitude,
        'longitude': item.longitude,
        'timezone': item.timezone,
        'channels': item.channels,
        'created_at': item.created_at,
    } for item in list_for_device(device.device_id)]}


@app.delete('/v1/alerts/subscriptions/{subscription_id}')
def remove_alert_subscription(request: Request, subscription_id: str, x_device_id: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    try:
        device = authenticate_device(x_device_id, authorization)
    except PermissionError:
        return error_response(request, 'unauthorized', 'Device authentication required.', False, 401)
    if not delete_subscription(subscription_id, device.device_id):
        return error_response(request, 'not_found', 'Subscription not found for this device.', False, 404)
    return {'deleted': True, 'id': subscription_id}
