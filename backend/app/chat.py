from datetime import datetime, timedelta
from json import loads
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from .models import ChatRequest, MS_TO_KMH
from .security import public_location, display_place_name
from .decision import recommendations_for_bundle, spray_window

SUPPORTED_LANGUAGES = ('en', 'hi', 'bn', 'te', 'mr', 'ta', 'gu', 'kn', 'ml', 'pa', 'or')
PHRASES = loads((Path(__file__).with_name('chat_phrases.json')).read_text(encoding='utf-8'))

TODAY_WORDS = (
    'today', 'aaj', 'आज', 'இன்று', 'আজ', 'ఈరోజు', 'ఈ రోజు', 'આજે', 'ಇಂದು', 'ഇന്ന്', 'ਅੱਜ', 'ଆଜି',
)
TOMORROW_WORDS = (
    'tomorrow', 'kal', 'कल', 'उद्या', 'நாளை', 'কাল', 'আগামীকাল', 'రేపు', 'કાલે', 'ನಾಳೆ', 'നാളെ', 'ਕੱਲ੍ਹ', 'କାଲି',
)
WEATHER_WORDS = TODAY_WORDS + TOMORROW_WORDS + (
    'weather', 'rain', 'temperature', 'wind', 'work', 'spray', 'morning', 'evening', 'afternoon',
    'tonight', 'weekend', 'next three hours', 'next 3 hours', 'today', 'tomorrow', 'mausam',
    'baarish', 'score', 'मौसम', 'बारिश', 'सुबह', 'शाम', 'दोपहर', 'আবহাওয়া', 'বৃষ্টি', 'তাপমাত্রা',
    'వాతావరణం', 'వర్షం', 'ఉష్ణోగ్రత', 'हवामान', 'पाऊस', 'तापमान', 'வானிலை', 'மழை', 'வெப்பநிலை',
    'હવામાન', 'વરસાદ', 'તાપમાન', 'ಹವಾಮಾನ', 'ಮಳೆ', 'ತಾಪಮಾನ', 'കാലാവസ്ഥ', 'മഴ', 'താപനില',
    'ਮੌਸਮ', 'ਮੀਂਹ', 'ਤਾਪਮਾਨ', 'ପାଣିପାଗ', 'ବର୍ଷା', 'ତାପମାତ୍ରା', 'अगले तीन घंटे',
)
ALERT_WORDS = (
    'alert', 'warning', 'चेतावनी', 'সতর্কতা', 'హెచ్చరిక', 'इशारे',
    'எச்சரிக்கை', 'ચેતવણી', 'ಎಚ್ಚರಿಕೆ', 'മുന്നറിയിപ്പ്', 'ਚੇਤਾਵਨੀ', 'ଚେତାବନୀ',
)
MARINE_WORDS = (
    'fish', 'marine', 'sea', 'wave', 'समुद्र', 'मछली', 'সমুদ্র', 'মাছ', 'సముద్ర', 'చేపల', 'मासे',
    'கடல்', 'மீன்', 'સમુદ્ર', 'માછી', 'ಸಮುದ್ರ', 'ಮೀನು', 'കടൽ', 'മത്സ്യ', 'ਸਮੁੰਦਰ', 'ਮੱਛੀ', 'ସମୁଦ୍ର', 'ମାଛ',
)
CLIMATE_WORDS = (
    'climate', 'years', 'monsoon', 'climate change', 'decade', 'hotter', 'जलवायु', 'साल',
)
COMPARE_WORDS = ('compare', 'तुलना', ' vs ', 'versus')
AGROMET_WORDS = ('agromet', 'advisory', 'कृषि सलाह', 'farming advisory')
# Decision / suitability questions — answer what to do before dumping stats.
ACTION_WORDS = (
    'should i', 'should we', 'can i', 'can we', 'is it safe', 'safe to', 'good time',
    'sow', 'sowing', 'seed', 'irrigat', 'spray', 'spraying', 'fish', 'fishing',
    'drive', 'driving', 'walk', 'hiking', 'dry clothes', 'outdoors', 'outdoor',
    'travel', 'travelling', 'traveling', 'work outside', 'field work', 'go out',
    'kheti', 'खेती', 'छिड़काव', 'सिंचाई', 'बुआई', 'बीज',
)


def is_action_question(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ACTION_WORDS)


def phrase(language: str, key: str, **kwargs) -> str:
    pack = PHRASES[key]
    template = pack.get(language) or pack['en']
    return template.format(**kwargs) if kwargs else template


def chat_language(language: str | None) -> str:
    return language if language in SUPPORTED_LANGUAGES else 'en'


SKIP_ADVICE_KEYS = {'advice_official_check', 'advice_stale'}


def format_recommendation(language: str, rec: dict) -> str:
    key = rec.get('key')
    if key in SKIP_ADVICE_KEYS:
        return ''
    params = dict(rec.get('params') or {})
    period = params.get('period')
    if period:
        period_key = f'period_{period}'
        if period_key in PHRASES:
            params['better'] = phrase(language, period_key)
    if key and key in PHRASES:
        safe = {}
        for name, value in params.items():
            if isinstance(value, str):
                safe[name] = value.replace('{', '').replace('}', '')
            elif isinstance(value, float) and value.is_integer():
                safe[name] = int(value)
            else:
                safe[name] = value
        try:
            return phrase(language, key, **safe) if safe else phrase(language, key)
        except (KeyError, ValueError, IndexError):
            return rec.get('message') or '' if language == 'en' else ''
    if language == 'en':
        return rec.get('message') or ''
    return ''


def grounded_advice_lines(request: ChatRequest, bundle: dict, rows: list | None = None) -> list[str]:
    recs = recommendations_for_bundle(
        rows or bundle.get('hourly') or [], request.profile, bundle, request.location.timezone,
    )
    lines = []
    for rec in recs:
        text = format_recommendation(chat_language(request.language), rec)
        if text and text not in lines:
            lines.append(text)
        if len(lines) >= 6:
            break
    return lines


def mentions(text: str, words: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in words)


def format_official_warning(language: str, alert: dict) -> str:
    headline = alert.get('headline') or alert.get('event') or 'Official weather warning'
    instruction = alert.get('instruction') or alert.get('description') or ''
    severity = alert.get('severity', 'unknown')
    expires = phrase(language, 'expires_suffix', expires=alert['expires']) if alert.get('expires') else ''
    return phrase(language, 'official_warning', headline=headline, severity=severity, instruction=instruction, expires=expires).strip()


def parse_hour_window(text: str, timezone_name: str, now: datetime | None = None):
    """Local clock window for questions like 'between 3 and 6'. Returns aware start/end or (None, None)."""
    zone = ZoneInfo(timezone_name)
    local_now = (now or datetime.now(zone)).astimezone(zone)
    match = re.search(
        r'(?:between\s+)?(\d{1,2})(?:\s*:\s*\d{2})?\s*(am|pm)?\s+(?:and|to)\s+(\d{1,2})(?:\s*:\s*\d{2})?\s*(am|pm)?',
        text,
        re.I,
    )
    if not match:
        return None, None

    def clock_hour(raw: str, period: str | None, other: str | None) -> int:
        hour = int(raw) % 24
        stamp = (period or other or '').lower()
        if stamp == 'pm' and hour < 12:
            hour += 12
        elif stamp == 'am' and hour == 12:
            hour = 0
        elif not stamp and 1 <= hour <= 7:
            hour += 12
        return hour

    start_hour = clock_hour(match.group(1), match.group(2), match.group(4))
    end_hour = clock_hour(match.group(3), match.group(4), match.group(2))
    start = local_now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    end = local_now.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


def select_time_rows(request: ChatRequest, bundle: dict, now: datetime | None = None):
    text = request.text.lower()
    zone = ZoneInfo(request.location.timezone)
    local_now = (now or datetime.now(zone)).astimezone(zone)
    window_start, window_end = parse_hour_window(text, request.location.timezone, local_now)
    if window_start and window_end:
        rows = [p for p in bundle['hourly'] if window_start <= datetime.fromisoformat(p['time']).astimezone(zone) < window_end]
        return rows, 0
    if any(x in text for x in ['next three hours', 'next 3 hours', 'अगले तीन घंटे']):
        end = local_now + timedelta(hours=3)
        return [p for p in bundle['hourly'] if local_now <= datetime.fromisoformat(p['time']).astimezone(zone) < end], 0
    offset = request.day_offset
    if mentions(text, TOMORROW_WORDS):
        offset = 1
    elif mentions(text, TODAY_WORDS):
        offset = 0
    if 'weekend' in text:
        days_to_saturday = (5 - local_now.weekday()) % 7
        dates = {local_now.date() + timedelta(days=days_to_saturday), local_now.date() + timedelta(days=days_to_saturday + 1)}
        return [p for p in bundle['hourly'] if datetime.fromisoformat(p['time']).astimezone(zone).date() in dates], days_to_saturday
    date = local_now.date()+timedelta(days=offset)
    rows = [p for p in bundle['hourly'] if datetime.fromisoformat(p['time']).astimezone(zone).date()==date]
    periods = [
        (['morning', 'सुबह', 'সকাল', 'காலை', 'ఉదయం', 'સવાર', 'ಬೆಳಿಗ್ಗೆ', 'രാവിലെ', 'ਸਵੇਰ', 'ସକାଳ'], 6, 12),
        (['afternoon', 'दोपहर', 'দুপুর', 'மதியம்', 'మధ్యాహ్నం'], 12, 17),
        (['evening', 'शाम', 'সন্ধ্যা', 'மாலை', 'సాయంత్రం', 'સાંજ', 'ಸಂಜೆ', 'വൈകുന്നേരം', 'ਸ਼ਾਮ', 'ସନ୍ଧ୍ୟା'], 17, 22),
        (['tonight', 'आज रात'], 18, 24),
    ]
    for words, lo, hi in periods:
        if any(w in text for w in words):
            rows = [p for p in rows if lo <= datetime.fromisoformat(p['time']).astimezone(zone).hour < hi]
    return rows, offset


def answer(request: ChatRequest, bundle: dict):
    text = request.text.lower()
    zone = ZoneInfo(request.location.timezone)
    rows, offset = select_time_rows(request, bundle)
    date = (datetime.now(zone).date()+timedelta(days=offset))
    language = chat_language(request.language)
    if mentions(text, ALERT_WORDS):
        official = bundle.get('official_alerts') or bundle.get('alerts') or []
        if official:
            message = '\n\n'.join(format_official_warning(language, alert) for alert in official)
        elif bundle.get('official_status')=='available' or bundle.get('alerts_status')=='available':
            message = phrase(language, 'alerts_none')
        else:
            message = phrase(language, 'alerts_unknown')
    elif mentions(text, MARINE_WORDS):
        message = phrase(language, 'marine_disclaimer')
    elif mentions(text, AGROMET_WORDS):
        message = phrase(language, 'agromet')
    elif any(w in text for w in ['spray', 'छिड़काव', 'स्प्रे']):
        spray = spray_window(rows or bundle.get('hourly') or [], request.location.timezone)
        hours = ', '.join(spray['suitable_hours_local'][:3])
        if hours:
            message = phrase(language, 'advice_spray_hours', hours=hours) + ' ' + phrase(language, 'spray')
        else:
            message = phrase(language, 'advice_spray_none') + ' ' + phrase(language, 'spray')
    elif mentions(text, COMPARE_WORDS):
        message = phrase(language, 'compare_need_second')
    elif mentions(text, CLIMATE_WORDS):
        message = phrase(language, 'climate_offline')
    elif not rows:
        message = phrase(language, 'unavailable')
    elif not mentions(text, WEATHER_WORDS) and not is_action_question(text):
        message = phrase(language, 'ask_weather')
    else:
        temps = [p['temperature'] for p in rows if p['temperature'] is not None]
        rain = [p['rain_chance'] for p in rows if p['rain_chance'] is not None]
        wind = [p['wind_ms'] for p in rows if p['wind_ms'] is not None]
        advice = grounded_advice_lines(request, bundle, rows or bundle.get('hourly') or [])
        # Filter repeated disagreement padding from the lead when answering actions.
        lead_advice = [
            line for line in advice
            if 'models differ' not in line.lower() and 'sources disagree' not in line.lower()
        ] or advice[:1]
        supporting: list[str] = []
        if temps:
            supporting.append(phrase(language, 'temperature', lo=min(temps), hi=max(temps)))
        if rain:
            supporting.append(phrase(language, 'rain', value=max(rain)))
        if wind:
            supporting.append(phrase(language, 'wind', value=max(wind) * MS_TO_KMH))
        if request.profile == 'farming' or 'spray' in text:
            supporting.append(phrase(language, 'spray'))

        parts: list[str] = []
        # Official warnings always first when present.
        official = bundle.get('official_alerts') or bundle.get('alerts') or []
        active_official = [a for a in official if a]
        if active_official and is_action_question(text):
            parts.append(format_official_warning(language, active_official[0]))
        if is_action_question(text):
            if lead_advice:
                parts.extend(lead_advice[:2])
            else:
                # Weather-wise decision frame without inventing crop thresholds.
                rain_max = max(rain) if rain else None
                if rain_max is not None and rain_max >= 60:
                    parts.append(
                        'Weather-wise, I would wait today — rain risk is high enough to disturb outdoor plans.'
                    )
                elif rain_max is not None and rain_max >= 35:
                    parts.append(
                        'It is probably okay with some risk — rain chances are moderate, so keep a flexible plan.'
                    )
                else:
                    parts.append(
                        'Weather-wise, conditions look reasonably suitable right now. '
                        'If you share more detail about the task or crop, I can make the advice more specific.'
                    )
            parts.append(f'{display_place_name(request.location.name)} · {date.isoformat()}')
            parts.extend(supporting)
            for rec in advice:
                if rec not in parts:
                    parts.append(rec)
                if len(parts) >= 8:
                    break
        else:
            parts.append(f'{display_place_name(request.location.name)} · {date.isoformat()}')
            parts.extend(supporting)
            for rec in advice:
                if rec not in parts:
                    parts.append(rec)
        parts.append(phrase(language, 'official'))
        message = '\n\n'.join(parts)
    if bundle['is_stale']:
        message = phrase(language, 'stale')+message
    intent = ('alerts' if mentions(text, ALERT_WORDS) else
        'marine' if mentions(text, MARINE_WORDS) else
        'rain' if mentions(text, ('rain', 'baarish', 'बारिश', 'বৃষ্টি', 'వర్షం', 'पाऊस', 'மழை', 'વરસાદ', 'ಮಳೆ', 'മഴ', 'ਮੀਂਹ', 'ବର୍ଷା')) else 'forecast')
    return {'answer':message, 'language':language, 'day_offset':offset,
        'retrieved_at':bundle['retrieved_at'], 'is_stale':bundle['is_stale'],
        'sources':bundle['sources'], 'agreement':bundle['agreement'],
        'conversation_context':{'conversation_id':str(request.conversation_id),
            'resolved_location':public_location(request.location), 'resolved_day_offset':offset,
            'profile':request.profile, 'last_intent':intent,
            'last_weather_context_id':bundle['retrieved_at']}}
