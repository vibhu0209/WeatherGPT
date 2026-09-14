# Alerts and local risk estimates

WeatherGPT keeps authoritative warnings and calculated forecast risks as separate data types.

Set `CAP_ALERT_URL` in the backend `.env` only to a trusted public CAP 1.2 feed or an RSS/Atom index of CAP documents (for example IMD `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` or NDMA SACHET India RSS). The service follows HTTPS allowlisted item links, parses CAP 1.2, accepts `Actual` alerts, rejects cancellations and expired or not-yet-effective entries, matches areas by polygon or circle when present, and falls back to areaDesc / geocode with an explicit `area_match_uncertain` flag when geometry is missing. Results are ordered by official severity. If the feed is absent, malformed, unreachable, or cannot be checked, the API reports `official_status: unavailable`; it never turns that state into “no warnings.”

For SIH disaster-management demos, `GET /v1/hazards/disaster-brief` (and chat tool `get_disaster_briefing`) compose an official-first board: CAP warnings → heavy-rain disruption estimate → road/landslide estimate → local risk thresholds → IMD/NDMA/SACHET links. WeatherGPT does not invent shelters, radar, or flood inundation maps.

WeatherGPT risk estimates use deterministic thresholds over validated forecast values (including a labelled waterlogging-disruption estimate from 24h rain totals). They are labelled `WEATHERGPT_RISK_ESTIMATE`, include the supporting value and rule, and never use the official-warning notification channel. Android users must opt in before local risk notifications are shown.

Android defines two channels: high-importance `official_warnings` for connected authoritative feeds, and default-importance `local_risks` for labelled WeatherGPT estimates. There is no unused daily-briefing channel. New warnings cannot arrive while the phone has no network connection.

Android stores a compact notification receipt after delivery. The receipt contains a namespaced alert/risk ID, SHA-256 content signature and timestamp. Repeated unchanged content is suppressed; meaningful content changes are eligible to notify again. Clearing all app data removes receipts.
