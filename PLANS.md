# Round 2 — contiguous work-window planner

## Phases
- [x] Git: work on `ignite` only; do not touch `main`.
- [x] Discovery of spray/harvest rules, tools, API, chat, tests.
- [x] Planner (`backend/app/work_window.py`) reusing `spray_window` / `harvest_window` thresholds.
- [x] Typed tool `get_work_window`.
- [x] GET `/v1/weather/work-window`.
- [x] Chat routing and English answer formatting.
- [x] Pytest coverage (planner, tool, route, chat) without network.
- [ ] Stretch: surface best window inside farming `recommendations` (optional, skipped unless required work is green).

## Acceptance
- Exclusive end = last qualifying hour + 1h; duration = count of hourly points.
- Missing hour or required field splits a run; min length default 2.
- `unavailable` vs `available` with empty windows are distinct.
- Stale + official alerts propagated honestly.
- Existing `spray_window`, `harvest_window`, `recommendations` unchanged.
- No Android, locale, or provider-config edits.

## Tests
Focused verification, 2026-10-22: `tests/test_work_window.py` — 20 passed.

Full verification, 2026-10-22: 248 passed, 1 third-party deprecation warning. Tests use a workspace-local pytest base temp directory because the system temp directory is not writable in this environment.
