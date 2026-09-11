from datetime import datetime, timezone

import httpx
import pytest

from app.alerts import AlertService, _rss_or_atom_links, parse_cap
from app.cache import MemoryCacheBackend
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


def test_rss_index_exposes_cap_document_links():
    rss = '''<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>Rain</title><link>https://cap-sources.s3.amazonaws.com/in-imd-en/sample.xml</link></item>
    <item><title>Wind</title><link>https://cap-sources.s3.amazonaws.com/in-imd-en/sample2.xml</link></item>
    </channel></rss>'''
    assert _rss_or_atom_links(rss) == [
        "https://cap-sources.s3.amazonaws.com/in-imd-en/sample.xml",
        "https://cap-sources.s3.amazonaws.com/in-imd-en/sample2.xml",
    ]


@pytest.mark.asyncio
async def test_official_alerts_are_cached_and_still_filtered_per_location(monkeypatch):
    """One feed fetch must serve many callers without widening the polygon filter."""
    service = AlertService(cache=MemoryCacheBackend(max_entries=8))
    monkeypatch.setattr(service.settings, 'cap_alert_url', 'https://cap.example.in/feed.xml')
    calls = {'count': 0}

    async def fake_network():
        calls['count'] += 1
        return [CAP]

    monkeypatch.setattr(service, '_documents', fake_network)
    inside = Location(name="Delhi", latitude=28.6, longitude=77.2)
    outside = Location(name="Mumbai", latitude=19.0, longitude=72.8)
    assert (await service.official(inside))['status'] == 'available'
    assert (await service.official(outside))['alerts'] == []


@pytest.mark.asyncio
async def test_document_cache_collapses_repeat_feed_fetches(monkeypatch):
    service = AlertService(cache=MemoryCacheBackend(max_entries=8))
    monkeypatch.setattr(service.settings, 'cap_alert_url', 'https://cap.example.in/feed.xml')
    monkeypatch.setattr(service.settings, 'cap_alert_allowed_hosts', 'cap.example.in')
    calls = {'count': 0}

    async def fake_fetch(client, index_xml):
        calls['count'] += 1
        return [CAP]

    class FakeResponse:
        text = '<rss version="2.0"><channel></channel></rss>'

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(service, '_fetch_cap_documents', fake_fetch)
    monkeypatch.setattr('app.alerts.httpx.AsyncClient', lambda **kwargs: FakeClient())

    delhi = Location(name="Delhi", latitude=28.6, longitude=77.2)
    for _ in range(5):
        assert (await service.official(delhi))['status'] == 'available'
    assert calls['count'] == 1, 'repeat requests for one area must reuse the cached authority feed'


@pytest.mark.asyncio
async def test_feed_outage_is_cached_briefly_and_never_implies_no_warnings(monkeypatch):
    service = AlertService(cache=MemoryCacheBackend(max_entries=8))
    monkeypatch.setattr(service.settings, 'cap_alert_url', 'https://cap.example.in/feed.xml')
    monkeypatch.setattr(service.settings, 'cap_alert_allowed_hosts', 'cap.example.in')
    calls = {'count': 0}

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            calls['count'] += 1
            raise httpx.ConnectError('feed down')

    monkeypatch.setattr('app.alerts.httpx.AsyncClient', lambda **kwargs: FailingClient())
    delhi = Location(name="Delhi", latitude=28.6, longitude=77.2)
    for _ in range(4):
        result = await service.official(delhi)
        assert result['status'] == 'unavailable'
        assert result['alerts'] == []
        assert 'does not mean there are no warnings' in result['message']
    assert calls['count'] == 1, 'a failing authority feed must not be re-hit on every request'
