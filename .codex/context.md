# WeatherGPT Round 2 — resume

Branch: `ignite` (do not commit to `main`).

## Contracts
- Hourly rows: dicts with ISO `time` (aware), `rain_chance`, `wind_ms`, `weather_code`, …
- Fusion (`weather.fuse`) keeps points from now−1h to now+7d, sorted by timestamp.
- Spray eligibility (`decision.spray_window`): rain ≤ 20 and wind ≤ 5; skip if either missing.
- Harvest eligibility (`decision.harvest_window`): rain ≤ 30, wind None or ≤ 8, code not in `{95,96,99}`.
- Thunder: `decision.THUNDER_CODES = {95, 96, 99}`.
- Stale: `bundle['is_stale']`. Official alerts: `alert_service.official` → `{status, alerts, message}`.
- Tools: `TOOL_REGISTRY` in `app/tools.py`; chat `select_tool` + `render_tool_result` in `chat_tools.py`.
- API location: Query `latitude`, `longitude`, `name`, `timezone`. Validation errors: 422 `{code, message, retryable, details}`.

## Planner
`plan_work_windows(hourly, activity, timezone_name, min_hours=2, now=...)`
`plan_from_bundle(bundle, activity, timezone, ...)`
Horizon: current UTC hour onward, max 48 points. Valid rows are sorted inside continuous input sections; missing, invalid, and duplicate timestamps are hard boundaries and are never silently bridged.
Avoid: rain_chance ≥ 60 OR thunderstorm code. Independent of activity.

## Integration
- Tool `get_work_window` / `WorkWindowInput`.
- Route `GET /v1/weather/work-window`.
- Chat: spray/harvest → `get_work_window`; English `format_work_window_answer`.
- Direct chat does not prepend a second stale-data notice because the planner formatter already makes stale data prominent.

## Do not change
`spray_window`, `harvest_window`, `recommendations` output; Android; 11 locale files; provider config.

## Verification (2026-10-22)
- `tests/test_work_window.py`: 19 passed.
- Full suite using workspace-local temp directory: 247 passed, 1 third-party deprecation warning.
- Regression repairs: rule persistence uses the user application-data directory; fixture time is dynamic; emergency landslide questions select the hazard tool before the broad emergency briefing; non-English templates bypass English-only layperson rewriting; warning-like place labels render only as `Selected place`.
