# Structured grounding and approved retrieval

WeatherGPT grounds numerical answers in typed weather, official-alert, marine, score and climate objects. Provider responses are validated and normalized before they reach deterministic chat. Gemini receives only the verified draft and may change wording only after number, unit, named-source and warning-severity validation. Structured JSON remains the source of truth for meteorological values.

No vector database is included. A retrieval system is appropriate only when approved explanatory documents become available, such as official warning instructions, IMD agromet advisories, reviewed safety guidance or climate definitions. Retrieved documents must retain issuer, canonical URL, publication/effective time, expiry when relevant, language, retrieval time and content hash. Expired or untrusted documents cannot override structured warnings or introduce forecast values.

The current CAP path preserves authority text directly as structured alerts. The application does not scrape arbitrary web advice into safety answers. Adding a document corpus requires an explicit source allowlist, licence review, update/withdrawal handling and tests proving that retrieved text cannot change validated weather numbers.
