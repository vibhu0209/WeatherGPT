# Alerts and local risk estimates

WeatherGPT keeps authoritative warnings and calculated forecast risks as separate data types.

Set `CAP_ALERT_URL` in the backend `.env` only to a trusted public CAP 1.2 feed or an RSS/Atom index of CAP documents (for example IMD `https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml` or NDMA SACHET India RSS). The service follows HTTPS allowlisted item links, parses CAP 1.2, accepts `Actual` alerts, rejects cancellations and expired or not-yet-effective entries, filters polygon areas for the requested location, and orders results by official severity. If the feed is absent, malformed, unreachable, or cannot be checked, the API reports `official_status: unavailable`; it never turns that state into “no warnings.” A production feed still needs source-specific area mapping, authentication if required, update/cancellation persistence, and live validation with the issuing authority.

WeatherGPT risk estimates use deterministic thresholds over validated forecast values. They are labelled `WEATHERGPT_RISK_ESTIMATE`, include the supporting value and rule, and never use the official-warning notification channel. Android users must opt in before local risk notifications are shown.

Android defines three channels: high-importance `official_warnings` reserved for connected authoritative feeds, default-importance `local_risks`, and low-importance `daily_forecast`. New warnings cannot arrive while the phone has no network connection.

Android stores a compact notification receipt after delivery. The receipt contains a namespaced alert/risk ID, SHA-256 content signature and timestamp. Repeated unchanged content is suppressed; meaningful content changes are eligible to notify again. Clearing all app data removes receipts.
