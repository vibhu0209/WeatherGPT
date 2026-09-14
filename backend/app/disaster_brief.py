"""Multi-hazard disaster briefing for SIH emergency / disaster-response demos.

Composes official CAP first, then labelled WeatherGPT estimates only.
Never invents shelters, radar, flood models, or NDMA geological verdicts.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .event_risk import assess_timed_event_risk, clock_window_label
from .models import Location
from .risks import estimate_risks
from .security import display_place_name


AUTHORITY_LINKS = (
    {
        'name': 'IMD Mausam',
        'url': 'https://mausam.imd.gov.in/',
        'role': 'Official meteorological warnings and forecasts',
    },
    {
        'name': 'NDMA',
        'url': 'https://ndma.gov.in/',
        'role': 'National disaster management guidance',
    },
    {
        'name': 'SACHET / NDMA alerts',
        'url': 'https://sachet.ndma.gov.in/',
        'role': 'Cell-broadcast / public alerting portal (when available)',
    },
)


def disruption_estimate(hourly: list[dict], location: Location) -> dict[str, Any] | None:
    """Next-window outdoor / waterlogging disruption from verified hourly rows."""
    rows = hourly[:6] or hourly[:12]
    if not rows:
        return None
    try:
        start = datetime.fromisoformat(rows[0]['time'])
        end = datetime.fromisoformat(rows[-1]['time'])
        label = clock_window_label(start, end)
    except (KeyError, TypeError, ValueError):
        label = 'the next few hours'
    assessment = assess_timed_event_risk(
        rows, place=display_place_name(location.name), window_label=label,
    )
    return {
        'classification': 'WEATHERGPT_RISK_ESTIMATE',
        'kind': 'heavy_rain_disruption',
        'decision': assessment['decision'],
        'severity': assessment['severity'],
        'score': assessment['score'],
        'factors': assessment.get('factors') or [],
        'inputs': assessment.get('inputs') or {},
        'window_label': label,
        'disclaimer': assessment.get('disclaimer'),
    }


def priority_actions(official_alerts: list[dict]) -> list[str]:
    actions: list[str] = []
    for alert in official_alerts[:3]:
        instruction = (alert.get('instruction') or '').strip()
        headline = (alert.get('headline') or alert.get('event') or '').strip()
        if instruction:
            actions.append(instruction)
        elif headline:
            actions.append(f'Follow official guidance for: {headline}')
        if alert.get('area_match_uncertain'):
            actions.append(
                'Area match for this official warning is uncertain — verify the district on IMD / SACHET before acting.'
            )
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for item in actions:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:5]


def compose_disaster_brief(
    *,
    location: Location,
    hourly: list[dict],
    official_status: str,
    official_alerts: list[dict],
    official_message: str | None,
    infrastructure_hazard: dict | None,
    retrieved_at: str | None = None,
    is_stale: bool = False,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Official-first multi-hazard board for emergency profile / SIH disaster demo."""
    alerts = list(official_alerts or [])
    risks = estimate_risks(hourly or [])
    disruption = disruption_estimate(hourly or [], location)
    now = retrieved_at or datetime.now(timezone.utc).isoformat()

    if alerts:
        lead = (
            f'OFFICIAL FIRST — {len(alerts)} active warning(s) for '
            f'{display_place_name(location.name)}. Follow authority instructions before any WeatherGPT estimate.'
        )
        posture = 'official_active'
    elif official_status == 'available':
        lead = (
            f'No active official CAP warning matched for {display_place_name(location.name)} right now. '
            f'That is not a guarantee — still check IMD / NDMA before field movement.'
        )
        posture = 'official_clear_matched'
    else:
        lead = (
            official_message
            or 'Official warning data could not be checked. This does not mean there are no warnings.'
        )
        posture = 'official_unavailable'

    layers: list[dict[str, Any]] = [
        {
            'order': 1,
            'id': 'official_cap',
            'title': 'Official warnings (CAP / IMD)',
            'priority': 'critical',
            'status': official_status,
            'items': alerts,
            'note': None if alerts else (
                'Unavailable does not mean safe.' if official_status != 'available'
                else 'No matched active CAP alert in the connected feed.'
            ),
        },
        {
            'order': 2,
            'id': 'disruption',
            'title': 'Heavy-rain / outdoor disruption estimate',
            'priority': 'high',
            'status': 'available' if disruption else 'unavailable',
            'items': [disruption] if disruption else [],
            'note': 'Forecast-based only — not a flood model or live radar.',
        },
        {
            'order': 3,
            'id': 'infrastructure',
            'title': 'Road / landslide connectivity estimate',
            'priority': 'high',
            'status': 'available' if infrastructure_hazard else 'unavailable',
            'items': [infrastructure_hazard] if infrastructure_hazard else [],
            'note': 'WeatherGPT estimate from rain, soil, DEM slope proxy, OSM — not NDMA geology.',
        },
        {
            'order': 4,
            'id': 'local_risks',
            'title': 'Local WeatherGPT risk thresholds',
            'priority': 'medium',
            'status': 'available' if risks else 'available',
            'items': risks,
            'note': 'Threshold estimates on validated hourly values — separate from official CAP.',
        },
    ]

    return {
        'classification': 'WEATHERGPT_DISASTER_BRIEF',
        'kind': 'multi_hazard_briefing',
        'place': display_place_name(location.name),
        'posture': posture,
        'lead': lead,
        'priority_actions': priority_actions(alerts),
        'layers': layers,
        'official_status': official_status,
        'official_alerts': alerts,
        'disruption_estimate': disruption,
        'infrastructure_hazard': infrastructure_hazard,
        'risk_estimates': risks,
        'authority_links': list(AUTHORITY_LINKS),
        'shelter_note': (
            'WeatherGPT does not list shelters or evacuation camps. '
            'Use official instruction text and local disaster authority / SACHET guidance for shelter decisions.'
        ),
        'disclaimer': (
            'Disaster briefing for situational awareness. Official CAP warnings outrank every WeatherGPT estimate. '
            'Not radar, not a hydrologic flood model, not an NDMA command dashboard.'
        ),
        'retrieved_at': now,
        'is_stale': is_stale,
        'sources': list(sources or []),
    }


def format_disaster_brief_answer(brief: dict) -> str:
    parts = [brief.get('lead') or 'Disaster briefing']
    actions = brief.get('priority_actions') or []
    if actions:
        parts.append('Priority actions from official text:')
        for action in actions[:3]:
            parts.append(f'• {action}')
    disruption = brief.get('disruption_estimate')
    if disruption:
        parts.append(disruption.get('decision') or '')
        for factor in (disruption.get('factors') or [])[:2]:
            parts.append(f'• {factor}')
    hazard = brief.get('infrastructure_hazard')
    if isinstance(hazard, dict) and hazard.get('decision'):
        parts.append(hazard['decision'])
        infra = hazard.get('infrastructure') or {}
        roads = infra.get('roads_at_risk_priority') or []
        if roads:
            names = ', '.join(str(item.get('name')) for item in roads[:4] if item.get('name'))
            if names:
                parts.append(f'Nearby roads to watch: {names}.')
    risks = brief.get('risk_estimates') or []
    for risk in risks[:2]:
        parts.append(f"{risk.get('message')} ({risk.get('rationale')})")
    parts.append(brief.get('shelter_note') or '')
    parts.append(brief.get('disclaimer') or '')
    links = brief.get('authority_links') or []
    if links:
        parts.append('Authority links: ' + '; '.join(f"{item['name']} {item['url']}" for item in links[:3]))
    return '\n\n'.join(part for part in parts if part)
