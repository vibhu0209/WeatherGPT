"""Groq tool-orchestration for chat. Facts come only from WeatherGPT tools."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from .chat import chat_language
from .chat import is_action_question
from .chat_tools import (
    _attach_tool,
    _forecast_answer,
    context,
    invoke_registered_tool,
    render_tool_result,
    select_tool,
)
from .groq_client import groq_client
from .models import ChatRequest
from .security import display_place_name, public_location, sanitize_llm_question
from .tools import TOOL_REGISTRY, ToolResult

_log = logging.getLogger('weathergpt.groq')
_ORCHESTRATOR_PROMPT = (Path(__file__).parents[1] / 'ai' / 'prompts' / 'orchestrator.md').read_text(encoding='utf-8')
_MAX_TOOL_ROUNDS = 4
_MAX_ANSWER_CHARS = 4000
# Keep prompts tight — avoid burning tokens on unused tool schemas.
_MAX_TOOL_RESULT_CHARS = 1800
_ACTIVE_ALERT_MARKER = '[ACTIVE_OFFICIAL_WARNING]'
_ALERT_STATUS_MARKER = '[OFFICIAL_WARNING_STATUS]'
_ACTION_SUPPORT_TOOLS = frozenset({'get_current_weather', 'get_hourly_forecast', 'get_daily_forecast'})

_TOOL_DESCRIPTIONS = {
    'get_current_weather': 'Verified current conditions and near-term forecast for the active place.',
    'get_hourly_forecast': (
        'Verified hourly forecast for timing questions, outdoor events (e.g. at 4 PM), '
        'heavy-rain / waterlogging disruption risk, and short grounded why-lines from forecast facts. '
        'Never claim radar anomalies or a municipal flood model.'
    ),
    'get_daily_forecast': 'Verified multi-day daily forecast for the active place.',
    'get_active_alerts': 'Official CAP/IMD-style warnings only. Never invent warnings.',
    'get_weather_score': 'Occupation suitability / Weather Score — prefer for should-I / can-I / safe-to / sow / irrigate / spray / outdoors / travel / drive / walk action questions.',
    'get_climate_summary': 'ERA5 climate trend summary (past years, not a forecast).',
    'get_marine_forecast': 'Model marine/wave state (not official INCOIS warnings). Prefer for fishing / sea questions.',
    'get_provider_status': 'Which weather providers are currently available.',
    'compare_locations': 'Compare verified forecasts for two places (needs secondary/saved places).',
    'get_saved_locations': 'List saved places already provided by the client.',
    'set_alert_rule': 'Describe saving a local alert rule preference (not a live government warning).',
    'get_agromet_advisory': 'Official agromet advisory status (often unavailable; do not invent crop advice).',
    'assess_infrastructure_hazard': (
        'Landslide / road-cut / infrastructure connectivity estimate from verified rainfall, '
        'Open-Meteo soil moisture, DEM slope proxy, and OpenStreetMap roads/villages. '
        'Use for landslide, mudslide, road collapse, cut-off villages, highway risk, GIS-style infrastructure questions. '
        'Always a WeatherGPT risk estimate — never an official NDMA/IMD geological verdict.'
    ),
    'get_disaster_briefing': (
        'Official-first multi-hazard disaster briefing for emergency / disaster-management questions: '
        'CAP warnings, heavy-rain disruption estimate, road/landslide estimate, local risk thresholds, '
        'and IMD/NDMA/SACHET links. Never invent shelters, radar, or flood inundation maps.'
    ),
}


def validate_grounded_answer(fact_context: str, candidate: str) -> bool:
    """Candidate may omit facts but must not invent numbers/units/severities/alerts."""
    if not candidate.strip():
        return False
    # Normalize narrow/no-break spaces Groq sometimes inserts between numbers and units.
    candidate = (
        candidate.replace('\u202f', ' ')
        .replace('\xa0', ' ')
        .replace('\u2009', ' ')
    )
    fact_context = (
        fact_context.replace('\u202f', ' ')
        .replace('\xa0', ' ')
        .replace('\u2009', ' ')
    )
    context_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', fact_context))
    answer_numbers = set(re.findall(r'(?<![\w])[-+]?\d+(?:\.\d+)?', candidate))
    if not _numbers_subset_allowing_rounding(answer_numbers, context_numbers):
        return False
    unit_pattern = r'(?<![\w])([-+]?\d+(?:\.\d+)?)\s*(°C|%|mm|m/s|km/h|m|seconds?|years?)(?!\w)'
    context_units = {(n, u.lower()) for n, u in re.findall(unit_pattern, fact_context, re.IGNORECASE)}
    answer_units = {(n, u.lower()) for n, u in re.findall(unit_pattern, candidate, re.IGNORECASE)}
    if not _units_subset_allowing_rounding(answer_units, context_units):
        return False
    lowered = candidate.lower()
    draft_lower = fact_context.lower()
    severities = ('yellow', 'orange', 'red', 'minor', 'moderate', 'severe', 'extreme')
    answer_sev = {term for term in severities if term in lowered}
    context_sev = {term for term in severities if term in draft_lower}
    if not answer_sev.issubset(context_sev):
        return False
    protected_terms = ('imd', 'incois', 'open-meteo', 'ecmwf', 'weathergpt risk estimate', 'official warning')
    if any(term in lowered and term not in draft_lower for term in protected_terms):
        return False
    if re.search(r'\bno (?:active |weather )?warnings?\b', lowered) and 'official' in draft_lower:
        if 'no active' not in draft_lower and 'no official' not in draft_lower and 'none' not in draft_lower:
            return False
    invented_warning = re.search(r'\b(evacuate|cyclone|tsunami|red alert)\b', lowered)
    if invented_warning and not re.search(invented_warning.group(0), draft_lower):
        return False
    return True


def _numbers_subset_allowing_rounding(answer_numbers: set[str], context_numbers: set[str]) -> bool:
    """Allow exact matches or rounding to a nearby verified value (e.g. 30 from 30.2)."""
    ctx_vals: list[float] = []
    for raw in context_numbers:
        try:
            ctx_vals.append(float(raw))
        except ValueError:
            continue
    for raw in answer_numbers:
        if raw in context_numbers:
            continue
        try:
            val = float(raw)
        except ValueError:
            return False
        if not any(abs(val - ctx) <= 0.51 for ctx in ctx_vals):
            return False
    return True


def _units_subset_allowing_rounding(
    answer_units: set[tuple[str, str]],
    context_units: set[tuple[str, str]],
) -> bool:
    by_unit: dict[str, list[float]] = {}
    for raw, unit in context_units:
        try:
            by_unit.setdefault(unit, []).append(float(raw))
        except ValueError:
            continue
    for raw, unit in answer_units:
        if (raw, unit) in context_units:
            continue
        try:
            val = float(raw)
        except ValueError:
            return False
        if not any(abs(val - ctx) <= 0.51 for ctx in by_unit.get(unit, [])):
            return False
    return True


def _openai_tools() -> list[dict[str, Any]]:
    tools = []
    for name in TOOL_REGISTRY:
        tools.append({
            'type': 'function',
            'function': {
                'name': name,
                'description': _TOOL_DESCRIPTIONS.get(name, name),
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'reason': {
                            'type': 'string',
                            'description': 'Brief why this tool is needed. No coordinates.',
                        },
                    },
                    'additionalProperties': False,
                },
            },
        })
    return tools


def _compact_context(request: ChatRequest) -> str:
    secondary = display_place_name(request.secondary_location.name) if request.secondary_location else None
    saved = [display_place_name(place.name) for place in (request.saved_locations or [])[:6]]
    return (
        f'Language: {request.language}\n'
        f'Occupation: {request.profile}\n'
        f'Place: {display_place_name(request.location.name)}\n'
        f'Day offset (0=today): {request.day_offset}\n'
        f'Secondary place: {secondary or "(none)"}\n'
        f'Saved places: {", ".join(saved) if saved else "(none)"}\n'
        f'Question: {sanitize_llm_question(request.text)}\n'
        'Call tools before stating weather facts. Coordinates are bound server-side.\n'
        'Prefer tools over guessing for any weather or infrastructure question.\n'
        'If this is an action / should-I question: decide first, then short reason, then supporting weather.\n'
        'If this is a landslide / road / cut-off / GIS infrastructure question: call assess_infrastructure_hazard.'
    )


def _serialize_tool_result(name: str, result: ToolResult, request: ChatRequest) -> dict[str, Any]:
    draft = render_tool_result(name, result, request)
    return {
        'tool': name,
        'status': result.status,
        'sources': result.sources,
        'is_stale': result.is_stale,
        'retrieved_at': result.retrieved_at,
        'verified_draft': draft['answer'][:_MAX_TOOL_RESULT_CHARS],
        'error': result.error,
    }


def _follow_ups_for(request: ChatRequest, tools: list[str]) -> list[str]:
    """Compact conversational chips — max 3, short labels."""
    profile = (request.profile or 'general').lower()
    if profile == 'farming':
        farming = {
            'get_hourly_forecast': ['Why this time?', 'Hourly', 'Warnings'],
            'get_weather_score': ['Best work time', 'Rain later?', 'Warnings'],
            'get_active_alerts': ['Best work time', 'Hourly', 'Tomorrow'],
            'get_daily_forecast': ['Hourly', 'Best work time', 'Warnings'],
        }
        picked: list[str] = []
        for tool in tools:
            for item in farming.get(tool, []):
                if item not in picked:
                    picked.append(item)
                if len(picked) >= 3:
                    return picked
        return (picked + ['Why this time?', 'Hourly', 'Warnings'])[:3]
    if profile == 'fishing':
        marine = {
            'get_marine_forecast': ['Wind & waves', 'Warnings', 'Tomorrow'],
            'get_active_alerts': ['Sea conditions', 'Wind & waves', 'Tomorrow'],
            'get_hourly_forecast': ['Sea conditions', 'Warnings', 'Tomorrow'],
        }
        picked = []
        for tool in tools:
            for item in marine.get(tool, []):
                if item not in picked:
                    picked.append(item)
                if len(picked) >= 3:
                    return picked
        return (picked + ['Sea conditions', 'Warnings', 'Tomorrow'])[:3]

    suggestions = {
        'get_active_alerts': ['Hourly', 'Tomorrow', 'Score'],
        'get_weather_score': ['Best time outside', 'Rain later?', 'Warnings'],
        'get_marine_forecast': ['Wind & waves', 'Warnings', 'Tomorrow'],
        'get_climate_summary': ['Tomorrow', 'Warnings', 'Hourly'],
        'compare_locations': ['Why this?', 'Tomorrow', 'Warnings'],
        'get_hourly_forecast': ['Why this time?', 'Warnings', 'Tomorrow'],
        'get_daily_forecast': ['Hourly', 'Warnings', 'Score'],
        'get_current_weather': ['Hourly', 'Warnings', 'Tomorrow'],
        'assess_infrastructure_hazard': ['Official warnings', 'Road risk', 'Rain later?'],
    }
    picked = []
    for tool in tools:
        for item in suggestions.get(tool, []):
            if item not in picked:
                picked.append(item)
            if len(picked) >= 3:
                return picked
    defaults = ['Hourly', 'Warnings', 'Tomorrow']
    for item in defaults:
        if item not in picked:
            picked.append(item)
        if len(picked) >= 3:
            break
    return picked[:3]


def _message_from_choice(payload: dict[str, Any]) -> dict[str, Any] | None:
    choices = payload.get('choices') or []
    if not choices:
        return None
    message = choices[0].get('message')
    return message if isinstance(message, dict) else None


async def _execute_tool(name: str, request: ChatRequest) -> tuple[dict[str, Any], dict | None, str]:
    """Returns (serialized_for_llm, last_payload_or_none, verified_draft)."""
    tool_request = request
    if (
        name == 'get_weather_score'
        and request.profile == 'general'
        and any(word in request.text.lower() for word in ('sow', 'seed', 'irrigat', 'spray'))
    ):
        tool_request = request.model_copy(update={'profile': 'farming'})
    if name == 'get_current_weather':
        draft = await _forecast_answer(tool_request, name)
        serialized = {
            'tool': name,
            'status': 'available',
            'sources': draft.get('sources') or [],
            'verified_draft': draft['answer'][:_MAX_TOOL_RESULT_CHARS],
        }
        return serialized, draft, draft['answer']

    try:
        result = await invoke_registered_tool(name, tool_request)
    except Exception as error:
        serialized = {'tool': name, 'status': 'unavailable', 'error': type(error).__name__}
        return serialized, None, ''

    if name == 'get_marine_forecast' and result.status == 'unavailable':
        draft = await _forecast_answer(tool_request, name)
        serialized = {
            'tool': name,
            'status': 'fallback_forecast',
            'verified_draft': draft['answer'][:_MAX_TOOL_RESULT_CHARS],
        }
        return serialized, draft, draft['answer']

    serialized = _serialize_tool_result(name, result, tool_request)
    payload = render_tool_result(name, result, tool_request)
    draft = serialized['verified_draft']
    if name == 'get_active_alerts':
        marker = _ACTIVE_ALERT_MARKER if isinstance(result.data, list) and bool(result.data) else _ALERT_STATUS_MARKER
        draft = f'{marker}\n{draft}'
    return serialized, payload, draft


def _prefer_action_draft(fact_chunks: list[str]) -> str:
    """When the LLM answer is rejected, avoid dumping conflicting tool leads."""
    chunks = [c.strip() for c in fact_chunks if c and c.strip()]
    if not chunks:
        return ''
    def _is_active_alert(text: str) -> bool:
        return text.startswith(_ACTIVE_ALERT_MARKER)

    def _clean_marker(text: str) -> str:
        if text.startswith(_ACTIVE_ALERT_MARKER):
            return text.removeprefix(_ACTIVE_ALERT_MARKER).lstrip()
        if text.startswith(_ALERT_STATUS_MARKER):
            return text.removeprefix(_ALERT_STATUS_MARKER).lstrip()
        return text

    if len(chunks) == 1:
        return _clean_marker(chunks[0])

    def _is_score(text: str) -> bool:
        return 'weather score' in text.lower() or 'score for' in text.lower()

    def _strip_lead(text: str) -> str:
        lines = [part.strip() for part in text.split('\n\n') if part.strip()]
        if not lines:
            return text
        lead = lines[0].lower()
        if lead.startswith((
            'weather-wise',
            'yes —',
            'yes -',
            "i'd wait",
            'i would wait',
            'it is probably',
        )):
            return '\n\n'.join(lines[1:]) or text
        return text

    alerts = [c for c in chunks if _is_active_alert(c)]
    alert_status = [c for c in chunks if c.startswith(_ALERT_STATUS_MARKER)]
    scores = [c for c in chunks if _is_score(c)]
    others = [c for c in chunks if c not in alerts and c not in alert_status and c not in scores]
    caution = next(
        (
            c for c in chunks
            if any(token in c.lower() for token in ("i'd wait", 'i would wait', 'less favourable', 'wait today', 'wait —', 'wait -'))
        ),
        None,
    )
    parts: list[str] = []
    if alerts:
        parts.append(_clean_marker(alerts[0]))
    if caution and caution not in alerts:
        # Prefer cautionary weather-window guidance over an optimistic score lead.
        parts.append(caution if not _is_score(caution) else caution)
        if scores and scores[0] not in parts:
            parts.append(_strip_lead(scores[0]))
        others = [c for c in others if c != caution]
    elif scores:
        parts.append(scores[0])
    elif others:
        parts.append(others[0])
        others = others[1:]
    for extra in others:
        body = _strip_lead(extra)
        if body and body not in parts:
            parts.append(body)
            break
    # A no-warning/unknown-status result is supporting context. It must not push the
    # user's decision below a status sentence. Include it only after the decision.
    if alert_status and parts:
        status = _clean_marker(alert_status[0])
        if status and status not in parts:
            parts.append(status)
    return '\n\n'.join(parts) if parts else '\n\n'.join(_clean_marker(c) for c in chunks)


async def _build_response(
    request: ChatRequest,
    *,
    used_tools: list[str],
    fact_chunks: list[str],
    last_payload: dict | None,
    answer_text: str,
    validator: str,
    started: float,
) -> dict:
    unique_tools = list(dict.fromkeys(used_tools))
    primary = unique_tools[-1] if unique_tools else select_tool(request)
    base = dict(last_payload or await _forecast_answer(request, primary))
    draft = _prefer_action_draft(fact_chunks) or base.get('answer', '')
    final = (answer_text or draft).strip()[:_MAX_ANSWER_CHARS]
    if not final:
        final = draft
    # If we fell back to tool text for an action question, prefer composed draft over raw join.
    if validator != 'pass' and answer_text and answer_text.strip() == '\n\n'.join(chunk for chunk in fact_chunks if chunk).strip():
        final = draft or final
    elif validator != 'pass' and (not answer_text or answer_text == '\n\n'.join(fact_chunks)):
        final = draft or final
    from .layperson import format_layperson_answer
    final = format_layperson_answer(final)
    suggestions = _follow_ups_for(request, unique_tools)
    duration_ms = int((time.monotonic() - started) * 1000)
    payload_out = _attach_tool({
        'answer': final,
        'language': chat_language(request.language),
        'day_offset': base.get('day_offset', request.day_offset),
        'retrieved_at': base.get('retrieved_at'),
        'is_stale': base.get('is_stale', False),
        'sources': base.get('sources') or [],
        'agreement': base.get('agreement', 'groq_orchestrated'),
        'follow_up_suggestions': suggestions,
        'used_tools': unique_tools,
        'response_origin': 'groq_tool_orchestrated',
        'conversation_context': {
            **context(request, base.get('retrieved_at') or '', primary),
            'used_tools': unique_tools,
            'response_origin': 'groq_tool_orchestrated',
            'resolved_location': public_location(request.location),
            'validator': validator,
        },
    }, primary)
    _log.info(
        'GROQ_SUCCESS MODE=orchestrator MODEL_NAME=%s latency_ms=%s tools=%s validator=%s response_origin=groq_tool_orchestrated FALLBACK_USED=%s',
        groq_client.model,
        duration_ms,
        ','.join(unique_tools) or 'none',
        validator,
        validator != 'pass',
    )
    return payload_out


async def orchestrate_chat(request: ChatRequest) -> dict | None:
    """Groq selects tools; WeatherGPT tools supply facts; Groq explains. None = fallback."""
    client = groq_client
    if not client.available():
        _log.info(
            'GROQ_FAILED reason=orchestrator_unavailable MODEL_NAME=%s FALLBACK_USED=True',
            client.model or 'none',
        )
        return None

    started = time.monotonic()
    _log.info('GROQ_STARTED MODE=orchestrator MODEL_NAME=%s', client.model)
    messages: list[dict[str, Any]] = [
        {'role': 'system', 'content': _ORCHESTRATOR_PROMPT},
        {'role': 'user', 'content': _compact_context(request)},
    ]
    used_tools: list[str] = []
    fact_chunks: list[str] = []
    last_payload: dict | None = None
    tools = _openai_tools()

    try:
        for round_index in range(_MAX_TOOL_ROUNDS):
            # After enough tools (or on the last round), ask for a final natural answer.
            tool_choice: str | dict[str, Any] = 'auto'
            use_tools = tools
            action_ready = (
                'get_weather_score' in used_tools
                and bool(_ACTION_SUPPORT_TOOLS.intersection(used_tools))
                and 'get_active_alerts' in used_tools
            )
            force_final = bool(used_tools) and (
                round_index == _MAX_TOOL_ROUNDS - 1
                or (is_action_question(request.text) and action_ready)
            )
            if force_final:
                tool_choice = 'none'
                use_tools = None
                if not any(
                    m.get('role') == 'user' and isinstance(m.get('content'), str) and str(m['content']).startswith('VERIFIED_ONLY')
                    for m in messages
                ):
                    messages.append({
                        'role': 'user',
                        'content': (
                            'VERIFIED_ONLY: Answer like a helpful local guide, not a data dump. '
                            'Use 2–4 short sentences. Lead with Yes / Maybe / No / Wait (or rain Yes/Maybe/Unlikely). '
                            'Then one plain reason. Put at most one number. '
                            'Do not paste weather-score lines, “supporting reading”, or long alert status text. '
                            'Keep numbers/units exact as in the drafts (do not invent). '
                            'Do not mention official warnings or all-clears '
                            'unless get_active_alerts appears in the tool results. '
                            'If drafts conflict, prefer official warnings, then the weather-score decision, '
                            'and use forecast numbers only as brief support.'
                        ),
                    })
            elif used_tools and messages and messages[-1].get('role') == 'tool':
                required_name: str | None = None
                if is_action_question(request.text):
                    missing = [
                        name for name in ('get_weather_score', 'get_hourly_forecast', 'get_active_alerts')
                        if name not in used_tools and not (name == 'get_hourly_forecast' and _ACTION_SUPPORT_TOOLS.intersection(used_tools))
                    ]
                    if missing:
                        required_name = missing[0]
                        tool_choice = 'required'
                # Soft nudge after tool results; model may call another tool or answer.
                if required_name:
                    messages.append({
                        'role': 'user',
                        'content': (
                            f'NEXT: Call {required_name} now so the action answer has verified decision, '
                            'supporting forecast, and official-warning context. Do not answer yet.'
                        ),
                    })
                elif not any(
                    m.get('role') == 'user' and isinstance(m.get('content'), str) and str(m['content']).startswith('NEXT:')
                    for m in messages
                ):
                    messages.append({
                        'role': 'user',
                        'content': (
                            'NEXT: If you need another tool, call it. Otherwise answer from verified drafts only. '
                            'Lead with what to do (weather-wise), not a raw stats dump. '
                            'Do not invent warnings or all-clears without get_active_alerts.'
                        ),
                    })

            payload = await client.chat_completions(
                messages=messages,
                tools=use_tools,
                tool_choice=tool_choice if use_tools else None,
                temperature=0.2,
                max_tokens=900,
            )
            if payload is None:
                _log.info('FALLBACK_USED reason=groq_http_or_skip MODEL_NAME=%s', client.model)
                return None

            message = _message_from_choice(payload)
            if message is None:
                _log.info('FALLBACK_USED reason=empty_choice MODEL_NAME=%s', client.model)
                return None

            tool_calls = message.get('tool_calls') or []
            # gpt-oss: take at most one tool call per round to stay compatible.
            if tool_calls and use_tools is not None:
                call = tool_calls[0]
                function = call.get('function') or {}
                name = (function.get('name') or '').strip()
                call_id = call.get('id') or f'call_{round_index}'
                # Append assistant message with the single tool call we honour.
                messages.append({
                    'role': 'assistant',
                    'content': message.get('content') or None,
                    'tool_calls': [call] if isinstance(call, dict) else tool_calls[:1],
                })
                if name not in TOOL_REGISTRY:
                    messages.append({
                        'role': 'tool',
                        'tool_call_id': call_id,
                        'content': json.dumps({'status': 'unavailable', 'error': 'unknown_tool'}),
                    })
                    continue

                serialized, tool_payload, draft = await _execute_tool(name, request)
                used_tools.append(name)
                if draft:
                    fact_chunks.append(draft)
                if tool_payload is not None:
                    last_payload = tool_payload
                messages.append({
                    'role': 'tool',
                    'tool_call_id': call_id,
                    'content': json.dumps(serialized, ensure_ascii=False)[:_MAX_TOOL_RESULT_CHARS + 200],
                })
                continue

            # Final natural-language answer path.
            content = (message.get('content') or '').strip()
            if not used_tools:
                _log.info('FALLBACK_USED reason=no_tools MODEL_NAME=%s', client.model)
                return None
            draft = '\n\n'.join(chunk for chunk in fact_chunks if chunk)
            composed = _prefer_action_draft(fact_chunks)
            if content and validate_grounded_answer(draft, content):
                return await _build_response(
                    request,
                    used_tools=used_tools,
                    fact_chunks=fact_chunks,
                    last_payload=last_payload,
                    answer_text=content,
                    validator='pass',
                    started=started,
                )
            # Forced final round or invented content — keep verified draft (composed for actions).
            validator = 'tool_loop_max' if use_tools is None else 'fallback_draft'
            _log.info(
                'FALLBACK_USED reason=validator_%s MODEL_NAME=%s latency_ms=%s',
                validator,
                client.model,
                int((time.monotonic() - started) * 1000),
            )
            return await _build_response(
                request,
                used_tools=used_tools,
                fact_chunks=fact_chunks,
                last_payload=last_payload,
                answer_text=composed or draft,
                validator=validator,
                started=started,
            )

        # Tool loop exhausted with facts collected — answer deterministically from tools.
        if used_tools and fact_chunks:
            _log.info(
                'FALLBACK_USED reason=tool_loop_max MODEL_NAME=%s latency_ms=%s',
                client.model,
                int((time.monotonic() - started) * 1000),
            )
            return await _build_response(
                request,
                used_tools=used_tools,
                fact_chunks=fact_chunks,
                last_payload=last_payload,
                answer_text=_prefer_action_draft(fact_chunks),
                validator='tool_loop_max',
                started=started,
            )
    except Exception as error:
        _log.info(
            'FALLBACK_USED reason=exception exception=%s MODEL_NAME=%s',
            type(error).__name__,
            client.model,
        )
        return None

    _log.info('FALLBACK_USED reason=tool_loop_or_empty MODEL_NAME=%s', client.model)
    return None
