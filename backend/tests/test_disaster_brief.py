from datetime import datetime, timezone

from app.alerts import parse_cap
from app.chat_tools import select_tool
from app.disaster_brief import compose_disaster_brief, format_disaster_brief_answer, priority_actions
from app.models import ChatRequest, Location
from app.risks import estimate_risks


LOC = Location(name='Delhi', latitude=28.6, longitude=77.2, timezone='Asia/Kolkata')


CIRCLE_CAP = '''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
<identifier>imd-circle</identifier><sender>imd@example.in</sender><sent>2026-09-07T08:00:00+05:30</sent>
<status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info>
<category>Met</category><event>Heavy Rain</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty>
<effective>2026-09-07T08:00:00+05:30</effective><expires>2026-09-08T08:00:00+05:30</expires>
<headline>Circle rain warning</headline><description>Heavy rain.</description><instruction>Avoid low-lying roads.</instruction>
<area><areaDesc>Delhi NCR</areaDesc><circle>28.6,77.2 40</circle></area>
</info></alert>'''


AREA_DESC_CAP = '''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
<identifier>imd-desc</identifier><sender>imd@example.in</sender><sent>2026-09-07T08:00:00+05:30</sent>
<status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info>
<category>Met</category><event>Thunderstorm</event><urgency>Immediate</urgency><severity>Moderate</severity><certainty>Likely</certainty>
<effective>2026-09-07T08:00:00+05:30</effective><expires>2026-09-08T08:00:00+05:30</expires>
<headline>Thunderstorm for Delhi</headline><description>Thunderstorm likely.</description><instruction>Stay indoors during lightning.</instruction>
<area><areaDesc>Delhi and adjoining districts</areaDesc></area>
</info></alert>'''


def test_cap_circle_includes_nearby_point():
    alerts = parse_cap(CIRCLE_CAP, LOC, datetime(2026, 9, 7, 8, tzinfo=timezone.utc))
    assert len(alerts) == 1
    assert alerts[0]['area_match'] == 'circle'
    assert alerts[0]['area_match_uncertain'] is False
    far = parse_cap(CIRCLE_CAP, Location(name='Mumbai', latitude=19.0, longitude=72.8), datetime(2026, 9, 7, 8, tzinfo=timezone.utc))
    assert far == []


def test_cap_area_desc_match_is_flagged_uncertain():
    alerts = parse_cap(AREA_DESC_CAP, LOC, datetime(2026, 9, 7, 8, tzinfo=timezone.utc))
    assert len(alerts) == 1
    assert alerts[0]['area_match'] == 'area_desc'
    assert alerts[0]['area_match_uncertain'] is True
    assert parse_cap(
        AREA_DESC_CAP,
        Location(name='Mumbai', latitude=19.0, longitude=72.8),
        datetime(2026, 9, 7, 8, tzinfo=timezone.utc),
    ) == []


def test_waterlogging_risk_from_24h_total():
    hourly = [{'time': f'2026-09-14T{hour:02d}:00:00+05:30', 'rain_mm': 5} for hour in range(12)]
    risks = estimate_risks(hourly)
    kinds = {item['kind'] for item in risks}
    assert 'waterlogging_disruption' in kinds


def test_disaster_brief_official_first():
    brief = compose_disaster_brief(
        location=LOC,
        hourly=[{'time': '2026-09-14T12:00:00+05:30', 'rain_chance': 90, 'rain_mm': 12, 'wind_ms': 4, 'temperature': 30}],
        official_status='available',
        official_alerts=[{
            'headline': 'Heavy rain warning', 'event': 'Rain', 'severity': 'severe',
            'instruction': 'Move away from flooded stretches.', 'area_match_uncertain': False,
        }],
        official_message=None,
        infrastructure_hazard={
            'decision': 'Elevated concern for nearby road cuts.',
            'infrastructure': {'roads_at_risk_priority': [{'name': 'NH-44'}]},
        },
    )
    assert brief['posture'] == 'official_active'
    assert 'OFFICIAL FIRST' in brief['lead']
    assert 'Move away from flooded stretches.' in priority_actions(brief['official_alerts'])
    answer = format_disaster_brief_answer(brief)
    assert 'OFFICIAL FIRST' in answer
    assert 'shelter' in answer.lower()
    assert 'ndma.gov.in' in answer.lower()


def test_disaster_briefing_tool_routing():
    assert select_tool(ChatRequest(
        text='Give me a disaster management situation report for responders',
        location=LOC,
        profile='emergency',
    )) == 'get_disaster_briefing'
    assert select_tool(ChatRequest(
        text='What is the emergency dashboard status?',
        location=LOC,
        profile='general',
    )) == 'get_disaster_briefing'
