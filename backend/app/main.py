from collections import defaultdict, deque
from datetime import datetime, timezone
import json
import logging
import time
import uuid
import httpx
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from .models import Location, ChatRequest
from .weather import service
from .chat import answer
from .decision import current_point, daily_summary, weather_score
from .climate import climate_service
from .risks import estimate_risks
from .alerts import alert_service
from .marine import marine_service
from .ai import gemini_polisher
from .language import language_service, BhashiniProvider, GoogleTranslationProvider

app = FastAPI(title='WeatherGPT', version='0.1.0')
app.add_middleware(GZipMiddleware, minimum_size=1000)
requests = defaultdict(deque)
audit_log = logging.getLogger('weathergpt.request')


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    return JSONResponse({'code':'validation_error','message':'Please check the information and try again.',
        'retryable':False,'request_id':getattr(request.state,'request_id',None),
        'details':[{'field':'.'.join(str(part) for part in item['loc'][1:]),'message':item['msg']} for item in error.errors()]},422)

@app.middleware('http')
async def limits(request: Request, call_next):
    started = time.monotonic()
    supplied = request.headers.get('x-request-id', '')
    request_id = supplied if 0 < len(supplied) <= 80 and supplied.replace('-', '').isalnum() else str(uuid.uuid4())
    request.state.request_id = request_id
    now = time.monotonic()
    ip = request.client.host if request.client else 'unknown'
    if len(requests)>4096: requests.clear()
    queue = requests[ip]
    while queue and queue[0]<now-60: queue.popleft()
    if len(queue)>=90:
        return JSONResponse({'code':'rate_limited','message':'Please wait a minute and try again.','retryable':True},429)
    queue.append(now)
    if request.method=='POST':
        body = await request.body()
        if len(body)>16384:
            return JSONResponse({'code':'too_large','message':'Please send a shorter message.','retryable':False},413)
    response = await call_next(request)
    response.headers['x-request-id'] = request_id
    audit_log.info(json.dumps({'event':'http_request','request_id':request_id,'method':request.method,
        'path':request.url.path,'status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000,1)}, separators=(',',':')))
    return response

@app.get('/health')
def health(): return {'status':'ok','time':datetime.now(timezone.utc).isoformat()}

@app.get('/v1/capabilities')
def capabilities():
    return {'forecast':True,'chat':'deterministic','official_alerts':bool(service.settings.cap_alert_url),'marine':True,
        'climate':True,'cloud_voice':False,'gemini':gemini_polisher.enabled,'demo_mode':False,
        'answer_languages':['en','hi']}

@app.get('/v1/languages/capabilities')
def language_capabilities():
    settings=service.settings
    providers=[BhashiniProvider(None,settings),GoogleTranslationProvider(None,settings)]
    return {'ui_languages':['en','hi','bn','te','mr','ta','gu','kn','ml','pa','or'],
        'providers':[provider.health() for provider in providers],
        'fallback':{'translation':'original text or English','asr':'Android installed recognizer','tts':'Android installed TTS'}}

async def finalize_chat(request: ChatRequest, result: dict):
    result['answer'] = await gemini_polisher.polish(request.text,result['answer'],result['language'])
    if request.language not in ('en','hi'):
        translated=await language_service.translate(result['answer'],'en',request.language)
        if not translated['fallback'] and __import__('app.ai',fromlist=['validate_polish']).validate_polish(result['answer'],translated['text']):
            result['answer']=translated['text'];result['language']=request.language
            result['language_provider']=translated['provider']
        else:
            result['language']='en';result['language_provider']='original'
    return result

@app.get('/v1/providers/status')
def providers():
    return {'providers':[p(None,service.settings).health() for p in __import__('app.providers',fromlist=['PROVIDERS']).PROVIDERS]}

@app.get('/v1/locations/search')
async def search(q: str = Query(min_length=2,max_length=100)):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get('https://geocoding-api.open-meteo.com/v1/search',params={'name':q,'count':8,'language':'en'})
            r.raise_for_status()
            return {'locations':[Location(name=', '.join(filter(None,[p['name'],p.get('admin1'),p.get('country')])),
                latitude=p['latitude'],longitude=p['longitude'],timezone=p.get('timezone','UTC')).model_dump()
                for p in r.json().get('results',[])]}
    except (httpx.HTTPError,ValueError,KeyError):
        return JSONResponse({'code':'unavailable','message':'Place search is unavailable. Please try again.','retryable':True},503)

@app.get('/v1/weather/bundle')
async def bundle(latitude: float=Query(ge=-90,le=90),longitude: float=Query(ge=-180,le=180),name: str=Query(default='Selected place',max_length=120),timezone: str='Asia/Kolkata'):
    try: loc=Location(name=name,latitude=latitude,longitude=longitude,timezone=timezone)
    except ValueError: return JSONResponse({'code':'invalid_location','message':'Please check the location and timezone.','retryable':False},422)
    data = await service.bundle(loc)
    official = await alert_service.official(loc)
    return {**data, 'alerts_status':official['status'], 'official_status':official['status'],
        'alerts':official['alerts'], 'official_alerts':official['alerts'], 'alerts_message':official['message']}

async def weather_for(latitude: float, longitude: float, name: str, timezone_name: str):
    return await service.bundle(Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone_name))

@app.get('/v1/weather/current')
async def current(latitude: float=Query(ge=-90,le=90), longitude: float=Query(ge=-180,le=180), name: str='Selected place', timezone: str='Asia/Kolkata'):
    data = await weather_for(latitude, longitude, name, timezone)
    return {key:data[key] for key in ('location','retrieved_at','is_stale','sources','source_count','agreement','provider_status')} | {'data': data.get('current') or current_point(data['hourly'])}

@app.get('/v1/weather/hourly')
async def hourly(latitude: float=Query(ge=-90,le=90), longitude: float=Query(ge=-180,le=180), name: str='Selected place', timezone: str='Asia/Kolkata', hours: int=Query(default=24,ge=1,le=168)):
    data = await weather_for(latitude, longitude, name, timezone)
    return {key:data[key] for key in ('location','retrieved_at','is_stale','sources','source_count','agreement','provider_status')} | {'data': data['hourly'][:hours]}

@app.get('/v1/weather/daily')
async def daily(latitude: float=Query(ge=-90,le=90), longitude: float=Query(ge=-180,le=180), name: str='Selected place', timezone: str='Asia/Kolkata', days: int=Query(default=7,ge=1,le=7)):
    data = await weather_for(latitude, longitude, name, timezone)
    summaries = data.get('daily') or daily_summary(data['hourly'], timezone)
    return {key:data[key] for key in ('location','retrieved_at','is_stale','sources','source_count','agreement','provider_status')} | {'data': summaries[:days]}

@app.get('/v1/weather/score')
async def score(latitude: float=Query(ge=-90,le=90), longitude: float=Query(ge=-180,le=180), name: str='Selected place', timezone: str='Asia/Kolkata', profile: str=Query(default='general',pattern='^(general|farming|fishing|outdoor)$')):
    data = await weather_for(latitude, longitude, name, timezone)
    return {'location':data['location'], 'retrieved_at':data['retrieved_at'], 'is_stale':data['is_stale'], 'data':data.get('scores',{}).get(profile) or weather_score(data['hourly'],profile), 'recommendations':data.get('recommendations',{}).get(profile,[])}

@app.get('/v1/weather/alerts')
async def alerts(latitude: float=Query(ge=-90,le=90), longitude: float=Query(ge=-180,le=180), name: str='Selected place', timezone: str='Asia/Kolkata'):
    data = await weather_for(latitude, longitude, name, timezone)
    official = await alert_service.official(Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone))
    return {
        'location': data['location'],
        'status':official['status'],
        'official_status':official['status'],
        'alerts':official['alerts'],
        'official_alerts':official['alerts'],
        'risk_estimates':data.get('risk_estimates') or estimate_risks(data['hourly']),
        'retrieved_at':data['retrieved_at'],
        'is_stale':data['is_stale'],
        'message':official['message'],
    }

@app.get('/v1/climate/summary')
async def climate_summary(latitude: float=Query(ge=-90,le=90), longitude: float=Query(ge=-180,le=180), name: str='Selected place', timezone: str='Asia/Kolkata', metric: str=Query(default='temperature',pattern='^(temperature|rainfall)$'), years: int=Query(default=10,ge=2,le=30)):
    try:
        data = await climate_service.summary(Location(name=name, latitude=latitude, longitude=longitude, timezone=timezone), metric, years)
        return {'data': data, 'is_stale': False}
    except httpx.HTTPError:
        return JSONResponse({'code':'climate_unavailable','message':'Historical climate data is unavailable. Please try again later.','retryable':True},503)
    except ValueError as error:
        return JSONResponse({'code':'insufficient_climate_data','message':str(error),'retryable':False},422)

@app.get('/v1/marine/forecast')
async def marine_forecast(latitude: float=Query(ge=-90,le=90), longitude: float=Query(ge=-180,le=180), name: str='Selected sea point', timezone: str='Asia/Kolkata', hours: int=Query(default=48,ge=1,le=168)):
    try:
        return await marine_service.forecast(Location(name=name,latitude=latitude,longitude=longitude,timezone=timezone),hours)
    except httpx.HTTPError:
        return JSONResponse({'code':'marine_unavailable','message':'Marine forecast data could not be checked. Check official IMD and INCOIS warnings.','retryable':True},503)
    except ValueError as error:
        return JSONResponse({'code':'marine_location_unavailable','message':str(error),'retryable':False},422)

@app.post('/v1/chat/message')
async def chat(request: ChatRequest):
    lowered = request.text.lower()
    if any(word in lowered for word in ('fish','marine','समुद्र','मछली')):
        try:
            result = await marine_service.forecast(request.location,48)
            rows = result['hourly'][:24]
            waves = [row['wave_height_m'] for row in rows if row['wave_height_m'] is not None]
            periods = [row['wave_period_s'] for row in rows if row['wave_period_s'] is not None]
            facts = [f"Marine model near {request.location.name} for the next 24 hours."]
            if waves: facts.append(f"Highest significant wave height: {max(waves):g} m.")
            if periods: facts.append(f"Longest mean wave period: {max(periods):g} seconds.")
            facts.append('This model is not a navigation or safety clearance. Check official IMD and INCOIS fishermen warnings before going to sea.')
            return await finalize_chat(request,{'answer':'\n\n'.join(facts),'language':'en','day_offset':request.day_offset,'retrieved_at':result['retrieved_at'],'is_stale':False,'sources':result['sources'],'agreement':'single_marine_model',
                'conversation_context':{'conversation_id':str(request.conversation_id),'resolved_location':request.location.model_dump(),'resolved_day_offset':request.day_offset,'profile':request.profile,'last_intent':'marine','last_weather_context_id':result['retrieved_at']}}
            )
        except (httpx.HTTPError,ValueError):
            pass
    if any(word in lowered for word in ('climate','hotter','years','monsoon','जलवायु','साल')):
        metric = 'rainfall' if any(word in lowered for word in ('rain','monsoon','बारिश')) else 'temperature'
        try:
            result = await climate_service.summary(request.location, metric, 10)
            unit = '°C per decade' if metric == 'temperature' else 'mm per decade'
            if request.language == 'hi':
                message = f"{request.location.name} के ERA5 पुनर्विश्लेषण में {result['period']['start_year']}–{result['period']['end_year']} का रुझान {result['trend_per_decade']:+g} {unit} है। डेटा कवरेज {result['coverage']*100:.1f}% है। यह कारण साबित नहीं करता और स्थानीय स्टेशन से अलग हो सकता है।"
            else:
                message = f"For {request.location.name}, ERA5 reanalysis shows a {result['trend_per_decade']:+g} {unit} trend from {result['period']['start_year']} to {result['period']['end_year']}. Data coverage is {result['coverage']*100:.1f}%. This does not attribute a cause and may differ from a local station."
            return await finalize_chat(request,{'answer':message,'language':request.language if request.language in ('en','hi') else 'en','day_offset':request.day_offset,'retrieved_at':result['generated_at'],'is_stale':False,'sources':[result['source']],'agreement':'single_reanalysis_source',
                'conversation_context':{'conversation_id':str(request.conversation_id),'resolved_location':request.location.model_dump(),
                    'resolved_day_offset':request.day_offset,'profile':request.profile,'last_intent':'climate','last_weather_context_id':result['generated_at']}}
            )
        except (httpx.HTTPError, ValueError):
            pass
    data = await service.bundle(request.location)
    result = answer(request,data)
    return await finalize_chat(request,result)
