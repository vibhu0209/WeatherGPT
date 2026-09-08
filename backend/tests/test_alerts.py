from datetime import datetime, timezone

from app.alerts import parse_cap
from app.models import Location


CAP = '''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
<identifier>imd-42</identifier><sender>imd@example.in</sender><sent>2026-09-07T08:00:00+05:30</sent>
<status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info>
<category>Met</category><event>Heavy Rain</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty>
<effective>2026-09-07T08:00:00+05:30</effective><expires>2026-09-08T08:00:00+05:30</expires>
<headline>Heavy rain warning</headline><description>Heavy rain is likely.</description><instruction>Stay away from flooded roads.</instruction>
<area><areaDesc>Delhi region</areaDesc><polygon>28.0,76.5 29.2,76.5 29.2,78.0 28.0,78.0 28.0,76.5</polygon></area>
</info></alert>'''


def test_cap_parses_active_official_warning_for_location():
    alerts = parse_cap(CAP, Location(name="Delhi", latitude=28.6, longitude=77.2), datetime(2026, 9, 7, 8, tzinfo=timezone.utc))
    assert len(alerts) == 1
    assert alerts[0]["classification"] == "OFFICIAL_WARNING"
    assert alerts[0]["severity"] == "severe"
    assert alerts[0]["instruction"] == "Stay away from flooded roads."


def test_cap_rejects_expired_and_outside_polygon():
    delhi = Location(name="Delhi", latitude=28.6, longitude=77.2)
    assert parse_cap(CAP, delhi, datetime(2026, 9, 9, tzinfo=timezone.utc)) == []
    assert parse_cap(CAP, Location(name="Mumbai", latitude=19.0, longitude=72.8), datetime(2026, 9, 7, 8, tzinfo=timezone.utc)) == []


def test_cap_cancel_never_surfaces_as_active():
    assert parse_cap(CAP.replace("<msgType>Alert</msgType>", "<msgType>Cancel</msgType>"), Location(name="Delhi", latitude=28.6, longitude=77.2), datetime(2026, 9, 7, 8, tzinfo=timezone.utc)) == []
