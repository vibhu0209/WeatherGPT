"""Turn verified tool drafts into short, plain answers for non-experts.

Facts stay grounded (numbers come from drafts). Style becomes conversational.
"""
from __future__ import annotations

import re


_BOILERPLATE = (
    re.compile(r'(?i)models differ'),
    re.compile(r'(?i)recommended window still stands'),
    re.compile(r'(?i)refresh before you leave'),
    re.compile(r'(?i)^if an imd warning is active for your area'),
    re.compile(r'(?i)^check official warnings before going out\.?$'),
    re.compile(r'(?i)^the connected official service reports'),
    re.compile(r'(?i)^official warnings? are not connected'),
    re.compile(r'(?i)^supporting inputs:'),
    re.compile(r'(?i)\(supporting detail\)'),
    re.compile(r'(?i)^no strong rain, heat or wind signal'),
    re.compile(r'(?i)^this score is guidance'),
    re.compile(r'(?i)^check local official warnings if you are heading out\.?$'),
    re.compile(r'(?i)^weathergpt risk estimate'),
)

_DECISION = re.compile(
    r'(?i)^(yes|no|maybe|unlikely|elevated|high concern|high disruption|watch|lower concern|'
    r'lower outdoor|weather-wise|i would wait|i\'d wait|comparing\b|official warning)'
)
_PLACE_DATE = re.compile(r'^.{1,48}·.{1,32}$')
_TEMP = re.compile(r'(?i)temperature:\s*([\d.]+)\s*to\s*([\d.]+)')
_RAIN_PCT = re.compile(
    r'(?i)(?:rain chance peaks around|some rain possible\s*[—\-–]?\s*about|'
    r'chance of rain[:\s]+|peaks around)\s*([\d.]+)\s*%'
)
_SCORE = re.compile(
    r'(?i)(?:supporting reading:|weather score for[^:]+:|overall it looks[^()]*\()'
    r'.*?(\d+)\s*(?:/|out of)\s*100'
)
_TIP = re.compile(
    r'(?i)(tell me the crop|choose the better|allow extra time|check the soil|'
    r'keep outdoor plans|carry|check rain and wind)'
)


def _rain_plain(pct: float) -> str:
    value = f'{pct:g}'
    if pct >= 60:
        return f'Rain is likely (about {value}% in the wettest hour).'
    if pct >= 35:
        return f'Some rain is possible (about {value}% at peak).'
    return f'Rain looks less likely (about {value}% at peak).'


def _temp_plain(lo: str, hi: str) -> str:
    return f'It will be about {lo}–{hi}°C.'


def _clean(line: str) -> str:
    return re.sub(r'\s+', ' ', line).strip()[:220]


def _is_place_only(line: str) -> bool:
    if any(ch.isdigit() for ch in line):
        return False
    if re.search(r'(?i)rain|temp|wind|°|%|mm|warning|score|sow|outside|concern|road|nearby', line):
        return False
    return len(line) <= 40 and '·' not in line


def format_layperson_answer(text: str) -> str:
    """Compress tool dumps into a short decision-first reply."""
    if not text or not text.strip():
        return text
    raw = (
        text.replace('\u2013', '-')
        .replace('\u00a0', ' ')
        .replace('\u202f', ' ')
        .strip()
    )
    lines = [_clean(line) for line in raw.splitlines() if _clean(line)]
    decision: str | None = None
    reasons: list[str] = []
    honesty: list[str] = []
    tip: str | None = None

    def add_reason(line: str) -> None:
        line = _clean(line)
        if not line or line in reasons or (decision and line == decision):
            return
        if len(reasons) < 3:
            reasons.append(line)

    def add_honesty(line: str) -> None:
        line = _clean(line)
        if not line or line in honesty:
            return
        if len(honesty) < 2:
            honesty.append(line)

    for line in lines:
        if any(pattern.search(line) for pattern in _BOILERPLATE):
            continue
        score = _SCORE.search(line)
        if score and ('out of 100' in line.lower() or '/100' in line.replace(' ', '')):
            add_reason(f"Overall it looks okay for your plan (about {score.group(1)} out of 100).")
            continue
        if re.search(r'(?i)about \d+ out of 100', line):
            add_reason(line)
            continue
        if _PLACE_DATE.match(line) and 'severity' not in line.lower():
            continue
        if _is_place_only(line):
            continue
        if re.match(r'(?i)^why\b', line):
            add_reason(line)
            continue
        if _DECISION.match(line):
            if decision is None:
                decision = _clean(re.sub(r'(?i)\s*·\s*severity\s+\w+.*$', '', line))
            continue
        if re.search(r'(?i)not a flood model|not live radar|radar is not available', line):
            add_honesty(line)
            continue
        if _TIP.search(line) and tip is None:
            tip = line[:160]
            continue
        temp = _TEMP.search(line)
        if temp:
            add_reason(_temp_plain(temp.group(1), temp.group(2)))
            continue
        rain = _RAIN_PCT.search(line)
        if rain:
            add_reason(_rain_plain(float(rain.group(1))))
            continue
        if re.match(r'(?i)^(?:nearby roads|nearby settlements|•)', line):
            add_reason(line.lstrip('• ').strip())
            continue
        if re.search(r'(?i)°c|km/h|%\b|wave|delhi|mumbai|chandigarh|pune|nh-?\d', line):
            add_reason(line)
            continue
        if re.match(r'(?i)^(?:highest )?wind\b|^marine\b|^alert rule\b|^saved\b|^providers\b', line):
            add_reason(line)
            continue
        if len(line) <= 200 and decision is None:
            decision = line
        elif len(line) <= 180:
            add_reason(line)

    parts: list[str] = []
    if decision:
        parts.append(decision)
    parts.extend(reasons[:3])
    parts.extend(honesty)
    if tip and tip not in parts:
        parts.append(tip)
    if not any('warning' in part.lower() or 'alert' in part.lower() for part in parts):
        if not any('radar' in part.lower() or 'flood model' in part.lower() for part in parts):
            parts.append('Check local official warnings if you are heading out.')

    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    substantive = [
        part for part in unique
        if not part.lower().startswith('check local official')
    ]
    if not substantive:
        light = [line for line in lines if not any(pattern.search(line) for pattern in _BOILERPLATE)]
        return '\n\n'.join(light[:5]) or lines[0]
    return '\n\n'.join(unique[:6])
