# AI and safety boundaries

Current chat always creates a deterministic verified draft first. If both `GEMINI_API_KEY` and `GEMINI_MODEL` are configured on the backend, Gemini may rewrite that draft in plain language using structured JSON. Android never receives the key. There is no fine-tuned model or cloud translation.

Weather claims come from validated structured provider values. Free text cannot directly set weather numbers. The response validator rejects any numeric token absent from the deterministic draft and rejects false “no warnings” claims. Malformed, unavailable, timed-out, or rejected Gemini output falls back to the unchanged deterministic draft. Broader entity/unit semantic validation remains in progress.

Official warnings have no live integration yet. The UI never labels missing warning data as “no warnings”. Fishing questions state that land forecasts cannot certify fishing safety. Farming wording refers to local agricultural advisories; crop-specific advice and safety scores are not generated.

Six typed deterministic tools, explicit conversation state, supplied-number validation, warning validation and cautious fallback are implemented. Gemini does not decide alerts or call providers directly. Prompting is not tuning. Do not activate paid cloud training without explicit authorization.
