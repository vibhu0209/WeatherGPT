from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .models import ChatRequest
from .security import public_location
from .decision import spray_window


def select_time_rows(request: ChatRequest, bundle: dict, now: datetime | None = None):
    text = request.text.lower()
    zone = ZoneInfo(request.location.timezone)
    local_now = (now or datetime.now(zone)).astimezone(zone)
    if any(x in text for x in ['next three hours', 'next 3 hours', 'अगले तीन घंटे']):
        end = local_now + timedelta(hours=3)
        return [p for p in bundle['hourly'] if local_now <= datetime.fromisoformat(p['time']).astimezone(zone) < end], 0
    offset = request.day_offset
    if any(x in text for x in ['tomorrow','kal','कल']): offset = 1
    elif any(x in text for x in ['today','आज','aaj']): offset = 0
    if 'weekend' in text:
        days_to_saturday = (5 - local_now.weekday()) % 7
        dates = {local_now.date() + timedelta(days=days_to_saturday), local_now.date() + timedelta(days=days_to_saturday + 1)}
        return [p for p in bundle['hourly'] if datetime.fromisoformat(p['time']).astimezone(zone).date() in dates], days_to_saturday
    date = local_now.date()+timedelta(days=offset)
    rows = [p for p in bundle['hourly'] if datetime.fromisoformat(p['time']).astimezone(zone).date()==date]
    periods = [(['morning','सुबह'],6,12), (['afternoon','दोपहर'],12,17), (['evening','शाम'],17,22), (['tonight','आज रात'],18,24)]
    for words, lo, hi in periods:
        if any(w in text for w in words):
            rows = [p for p in rows if lo <= datetime.fromisoformat(p['time']).astimezone(zone).hour < hi]
    return rows, offset


def answer(request: ChatRequest, bundle: dict):
    text = request.text.lower()
    zone = ZoneInfo(request.location.timezone)
    rows, offset = select_time_rows(request, bundle)
    date = (datetime.now(zone).date()+timedelta(days=offset))
    hindi = request.language=='hi'
    if any(w in text for w in ['alert','warning','चेतावनी']):
        official = bundle.get('official_alerts') or bundle.get('alerts') or []
        if official:
            parts=[]
            for alert in official:
                headline=alert.get('headline') or alert.get('event') or ('आधिकारिक मौसम चेतावनी' if hindi else 'Official weather warning')
                instruction=alert.get('instruction') or alert.get('description') or ''
                severity=alert.get('severity','unknown')
                expires=alert.get('expires')
                if hindi:
                    parts.append(f"आधिकारिक चेतावनी: {headline}। गंभीरता: {severity}। {instruction}"+(f" समाप्ति: {expires}।" if expires else ''))
                else:
                    parts.append(f"Official warning: {headline}. Severity: {severity}. {instruction}"+(f" Expires: {expires}." if expires else ''))
            message='\n\n'.join(parts)
        elif bundle.get('official_status')=='available' or bundle.get('alerts_status')=='available':
            message = 'इस समय जुड़ी आधिकारिक सेवा में कोई सक्रिय चेतावनी नहीं मिली। अपडेट के लिए दोबारा जाँचें।' if hindi else 'The connected official service reports no active warning at this time. Refresh for updates.'
        else:
            message = 'आधिकारिक चेतावनी उपलब्धता पता नहीं है। बाहर जाने से पहले IMD की चेतावनी देखें।' if hindi else 'Official warning availability is unknown. Check the IMD warning for your area before going out.'
    elif any(w in text for w in ['fish','marine','समुद्र','मछली']):
        message = 'Ask about marine conditions while online for wave-height model guidance. Official IMD and INCOIS fishermen warnings still take precedence. Land weather cannot tell you whether fishing is safe.'
    elif any(w in text for w in ['agromet','advisory','कृषि सलाह']):
        message = 'Official IMD agromet advisory text is not connected. Use the farming weather score and local agricultural advice. Do not invent crop-specific guidance.'
    elif any(w in text for w in ['spray','छिड़काव','स्प्रे']):
        spray = spray_window(rows or bundle.get('hourly') or [], request.location.timezone)
        message = spray['message'] + ' ' + spray['disclaimer']
    elif any(w in text for w in ['compare','तुलना','vs ']):
        message = 'To compare places, include a second location with your question. WeatherGPT compares verified daily forecasts only.'
    elif any(w in text for w in ['climate','years','monsoon','climate change']):
        message = 'Historical climate trends use live ERA5 reanalysis. Reconnect online and ask again — short forecasts cannot invent climate trends.'
    elif not rows:
        message = 'इस समय का मौसम उपलब्ध नहीं है। इंटरनेट से जुड़कर फिर कोशिश करें।' if hindi else 'Weather for that time is unavailable. Connect to the internet and try again.'
    elif not any(w in text for w in ['weather','rain','temperature','wind','work','spray','morning','evening','afternoon','tonight','weekend','next three hours','next 3 hours','today','tomorrow','mausam','baarish','kal','मौसम','बारिश','कल','आज','सुबह','शाम']):
        message = 'Ask about weather, rain, temperature, or wind today or tomorrow. Choose a question below to begin.'
    else:
        temps = [p['temperature'] for p in rows if p['temperature'] is not None]
        rain = [p['rain_chance'] for p in rows if p['rain_chance'] is not None]
        wind = [p['wind_ms'] for p in rows if p['wind_ms'] is not None]
        parts = [f'{request.location.name} · {date.isoformat()}']
        if temps: parts.append(f'तापमान {min(temps):g} से {max(temps):g}°C।' if hindi else f'Temperature: {min(temps):g} to {max(temps):g}°C.')
        if rain: parts.append(f'बारिश की सबसे अधिक संभावना {max(rain):g}% है।' if hindi else f'Highest hourly chance of rain: {max(rain):g}%.')
        if wind: parts.append(f'हवा की अधिकतम गति {max(wind)*3.6:.0f} किमी/घंटा।' if hindi else f'Highest wind speed: {max(wind)*3.6:.0f} km/h.')
        if request.profile=='farming' or 'spray' in text:
            parts.append('फसल पर छिड़काव से पहले स्थानीय कृषि सलाह देखें।' if hindi else 'Check your local agricultural advisory before spraying crops.')
        parts.append('बाहर जाने से पहले आधिकारिक चेतावनी देखें।' if hindi else 'Check official warnings before going out.')
        message = '\n\n'.join(parts)
    if bundle['is_stale']:
        message = ('पुराना सहेजा हुआ मौसम — जानकारी बदल सकती है।\n\n' if hindi else 'Saved forecast — conditions may have changed.\n\n')+message
    intent = ('alerts' if any(w in text for w in ['alert','warning','चेतावनी']) else
        'marine' if any(w in text for w in ['fish','marine','समुद्र','मछली']) else
        'rain' if any(w in text for w in ['rain','baarish','बारिश']) else 'forecast')
    return {'answer':message, 'language':'hi' if hindi else 'en', 'day_offset':offset,
        'retrieved_at':bundle['retrieved_at'], 'is_stale':bundle['is_stale'],
        'sources':bundle['sources'], 'agreement':bundle['agreement'],
        'conversation_context':{'conversation_id':str(request.conversation_id),
            'resolved_location':public_location(request.location), 'resolved_day_offset':offset,
            'profile':request.profile, 'last_intent':intent,
            'last_weather_context_id':bundle['retrieved_at']}}

