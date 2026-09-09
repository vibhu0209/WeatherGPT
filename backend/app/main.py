from datetime import datetime, timezone
import json
import hashlib
import math
import logging
import uuid
import httpx
from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from .models import Location, ChatRequest, Settings
from .weather import service
from .chat import answer
from .decision import current_point, daily_summary, weather_score
from .climate import climate_service
from .risks import estimate_risks
from .alerts import alert_service
from .marine import marine_service
from .ai import gemini_polisher
from .language import language_service, BhashiniProvider, GoogleTranslationProvider
from .subscriptions import (
    authenticate as authenticate_device,
    create as create_subscription,
    delete as delete_subscription,
    list_for_device,
    register as register_device_record,
    revoke as revoke_device,
)
from .security import SlidingWindowLimiter, public_location
from pydantic import BaseModel, Field

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
rate_limiter = SlidingWindowLimiter(limit=90, window_seconds=60, max_keys=4096)
audit_log = logging.getLogger('weathergpt.request')


def error_response(request: Request | None, code: str, message: str, retryable: bool, status: int):
    request_id = getattr(getattr(request, 'state', None), 'request_id', None)
    return JSONResponse({'code': code, 'message': message, 'retryable': retryable, 'request_id': request_id}, status)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    return JSONResponse({'code': 'validation_error', 'message': 'Please check the information and try again.',
        'retryable': False, 'request_id': getattr(request.state, 'request_id', None),
        'details': [{'field': '.'.join(str(part) for part in item['loc'][1:]), 'message': item['msg']} for item in error.errors()]}, 422)


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
    if not rate_limiter.allow(ip):
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
    return {
        'status': 'ready',
        'cache': 'memory',
        'gemini': gemini_polisher.enabled,
        'cap_alerts': bool(service.settings.cap_alert_url),
        'time': datetime.now(timezone.utc).isoformat(),
    }


@app.get('/v1/capabilities')
def capabilities():
    return {'forecast': True, 'chat': 'deterministic', 'official_alerts': bool(service.settings.cap_alert_url), 'marine': True,
        'climate': True, 'cloud_voice': False, 'gemini': gemini_polisher.enabled, 'demo_mode': False,
        'answer_languages': ['en', 'hi']}


@app.get('/v1/languages/capabilities')
def language_capabilities():
    settings = service.settings
    providers = [BhashiniProvider(None, settings), GoogleTranslationProvider(None, settings)]
    return {'ui_languages': ['en', 'hi', 'bn', 'te', 'mr', 'ta', 'gu', 'kn', 'ml', 'pa', 'or'],
        'providers': [provider.health() for provider in providers],
        'fallback': {'translation': 'original text or English', 'asr': 'Android installed recognizer', 'tts': 'Android installed TTS'}}


async def finalize_chat(request: ChatRequest, result: dict):
    result['answer'] = await gemini_polisher.polish(request.text, result['answer'], result['language'])
    if request.language not in ('en', 'hi'):
        translated = await language_service.translate(result['answer'], 'en', request.language)
        if not translated['fallback'] and __import__('app.ai', fromlist=['validate_polish']).validate_polish(result['answer'], translated['text']):
            result['answer'] = translated['text']
            result['language'] = request.language
            result['language_provider'] = translated['provider']
        else:
            result['language'] = 'en'
            result['language_provider'] = 'original'
    if 'conversation_context' in result and 'resolved_location' in result['conversation_context']:
        result['conversation_context']['resolved_location'] = public_location(request.location)
    return result


@app.get('/v1/providers/status')
def providers():
    return {'providers': [p(None, service.settings).health() for p in __import__('app.providers', fromlist=['PROVIDERS']).PROVIDERS]}


@app.get('/v1/locations/search')
async def search(request: Request, q: str = Query(min_length=2, max_length=100), language: str = Query(default='en', pattern='^(en|hi|bn|te|mr|ta|gu|kn|ml|pa|or)$')):
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            r = await client.get('https://geocoding-api.open-meteo.com/v1/search', params={'name': q, 'count': 8, 'language': language})
            r.raise_for_status()
            return {'locations': [Location(name=', '.join(filter(None, [p['name'], p.get('admin1'), p.get('country')])),
                latitude=p['latitude'], longitude=p['longitude'], timezone=p.get('timezone', 'UTC')).model_dump()
                for p in r.json().get('results', [])]}
    except (httpx.HTTPError, ValueError, KeyError):
        return error_response(request, 'unavailable', 'Place search is unavailable. Please try again.', True, 503)


class LocationBody(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str = Field(default='Current location', min_length=1, max_length=120)


class BundleBody(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str = Field(default='Selected place', min_length=1, max_length=120)
    timezone: str = Field(default='Asia/Kolkata', max_length=64)
    hours: int = Field(default=168, ge=24, le=168)


async def _resolve_location(request: Request, latitude: float, longitude: float, name: str):
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.get('https://api.open-meteo.com/v1/forecast', params={
                'latitude': latitude, 'longitude': longitude, 'timezone': 'auto', 'forecast_days': 1, 'hourly': 'temperature_2m'})
            response.raise_for_status()
            timezone_name = response.json()['timezone']
            location = Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone_name)
            return {'location': location.model_dump()}
    except (httpx.HTTPError, ValueError, KeyError):
        return error_response(request, 'location_unavailable', 'The location timezone could not be checked. Please search for your village or city.', True, 503)


@app.get('/v1/locations/resolve')
async def resolve_location(request: Request, latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180), name: str = Query(default='Current location', max_length=120)):
    return await _resolve_location(request, latitude, longitude, name)


@app.post('/v1/locations/resolve')
async def resolve_location_post(request: Request, body: LocationBody):
    return await _resolve_location(request, body.latitude, body.longitude, body.name)


async def _weather_bundle(request: Request, response: Response, latitude: float, longitude: float, name: str, timezone_name: str, hours: int):
    try:
        loc = Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone_name)
    except ValueError:
        return error_response(request, 'invalid_location', 'Please check the location and timezone.', False, 422)
    data = await service.bundle(loc)
    official = await alert_service.official(loc)
    payload = {**data, 'hourly': data.get('hourly', [])[:hours], 'daily': data.get('daily', [])[:math.ceil(hours / 24)],
        'alerts_status': official['status'], 'official_status': official['status'],
        'alerts': official['alerts'], 'official_alerts': official['alerts'], 'alerts_message': official['message']}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    etag = f'"{digest}"'
    headers = {'etag': etag, 'cache-control': 'private, max-age=300'}
    if request.headers.get('if-none-match') == etag:
        return Response(status_code=304, headers=headers)
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
    lowered = request.text.lower()
    if any(word in lowered for word in ('compare', 'तुलना', ' vs ')) and request.secondary_location is not None:
        from .tools import CompareInput, compare_locations
        compared = await compare_locations(CompareInput(locations=[request.location, request.secondary_location], day_offset=request.day_offset))
        parts = ['Comparing verified daily forecasts:']
        for item in (compared.data or {}).get('comparisons', []):
            day = item.get('daily') or {}
            place = (item.get('location') or {}).get('name', 'Place')
            if day:
                parts.append(
                    f"{place}: high {day.get('temperature_max')}°C, rain chance {day.get('rain_chance_max')}%, "
                    f"wind {None if day.get('wind_max_ms') is None else round(day['wind_max_ms']*3.6)} km/h."
                )
            else:
                parts.append(f'{place}: daily forecast unavailable.')
        parts.append('Official warnings still take precedence for each place.')
        return await finalize_chat(request, {
            'answer': '\n'.join(parts), 'language': 'en', 'day_offset': request.day_offset,
            'retrieved_at': compared.retrieved_at, 'is_stale': compared.is_stale, 'sources': compared.sources,
            'agreement': 'multi_location_compare',
            'conversation_context': {
                'conversation_id': str(request.conversation_id), 'resolved_location': public_location(request.location),
                'resolved_day_offset': request.day_offset, 'profile': request.profile, 'last_intent': 'compare',
                'last_weather_context_id': compared.retrieved_at,
            },
        })
    if any(word in lowered for word in ('fish', 'marine', 'समुद्र', 'मछली')):
        try:
            result = await marine_service.forecast(request.location, 48)
            rows = result['hourly'][:24]
            waves = [row['wave_height_m'] for row in rows if row['wave_height_m'] is not None]
            periods = [row['wave_period_s'] for row in rows if row['wave_period_s'] is not None]
            official = await alert_service.official(request.location)
            facts = []
            official_sources = []
            if official['alerts']:
                for alert in official['alerts']:
                    facts.append(f"Official warning: {alert['headline']}. Severity: {alert['severity']}. {alert.get('instruction') or alert.get('description') or ''}" + (f" Expires: {alert['expires']}." if alert.get('expires') else ''))
                    if alert.get('sender'):
                        official_sources.append(alert['sender'])
            elif official['status'] != 'available':
                facts.append('Official fishermen-warning availability is unknown. Check IMD and INCOIS before going to sea.')
            else:
                facts.append('The connected official feed reports no active warning here. Refresh before going to sea.')
            facts.append(f'Marine model near {request.location.name} for the next 24 hours.')
            if waves:
                facts.append(f'Highest significant wave height: {max(waves):g} m.')
            if periods:
                facts.append(f'Longest mean wave period: {max(periods):g} seconds.')
            facts.append('This model is not a navigation or safety clearance. Check official IMD and INCOIS fishermen warnings before going to sea.')
            return await finalize_chat(request, {'answer': '\n\n'.join(facts), 'language': 'en', 'day_offset': request.day_offset, 'retrieved_at': result['retrieved_at'], 'is_stale': False, 'sources': result['sources'] + list(dict.fromkeys(official_sources)), 'agreement': 'single_marine_model',
                'conversation_context': {'conversation_id': str(request.conversation_id), 'resolved_location': public_location(request.location), 'resolved_day_offset': request.day_offset, 'profile': request.profile, 'last_intent': 'marine', 'last_weather_context_id': result['retrieved_at']}}
            )
        except (httpx.HTTPError, ValueError):
            pass
    if any(word in lowered for word in ('climate', 'hotter', 'years', 'monsoon', 'जलवायु', 'साल')):
        metric = 'rainfall' if any(word in lowered for word in ('rain', 'monsoon', 'बारिश')) else 'temperature'
        try:
            result = await climate_service.summary(request.location, metric, 10)
            unit = '°C per decade' if metric == 'temperature' else 'mm per decade'
            if request.language == 'hi':
                message = f"{request.location.name} के ERA5 पुनर्विश्लेषण में {result['period']['start_year']}–{result['period']['end_year']} का रुझान {result['trend_per_decade']:+g} {unit} है। डेटा कवरेज {result['coverage']*100:.1f}% है। यह कारण साबित नहीं करता और स्थानीय स्टेशन से अलग हो सकता है।"
            else:
                message = f"For {request.location.name}, ERA5 reanalysis shows a {result['trend_per_decade']:+g} {unit} trend from {result['period']['start_year']} to {result['period']['end_year']}. Data coverage is {result['coverage']*100:.1f}%. This does not attribute a cause and may differ from a local station."
            return await finalize_chat(request, {'answer': message, 'language': request.language if request.language in ('en', 'hi') else 'en', 'day_offset': request.day_offset, 'retrieved_at': result['generated_at'], 'is_stale': False, 'sources': [result['source']], 'agreement': 'single_reanalysis_source',
                'conversation_context': {'conversation_id': str(request.conversation_id), 'resolved_location': public_location(request.location),
                    'resolved_day_offset': request.day_offset, 'profile': request.profile, 'last_intent': 'climate', 'last_weather_context_id': result['generated_at']}}
            )
        except (httpx.HTTPError, ValueError):
            pass
    data = await service.bundle(request.location)
    official = await alert_service.official(request.location)
    data = {**data, 'official_status': official['status'], 'alerts_status': official['status'], 'official_alerts': official['alerts'], 'alerts': official['alerts']}
    result = answer(request, data)
    return await finalize_chat(request, result)


class DeviceRegistration(BaseModel):
    device_id: str | None = Field(default=None, min_length=8, max_length=80)


class AlertSubscriptionRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(default='Asia/Kolkata', max_length=64)
    channels: list[str] = Field(default_factory=lambda: ['severe'])


@app.post('/v1/device/register')
def register_device(body: DeviceRegistration | None = None):
    return register_device_record(body.device_id if body else None)


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
