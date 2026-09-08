# WeatherGPT
- Work directly in D:/WeatherGPT. The pre-existing nested WeatherGPT directory is not the application root.
- Native Kotlin/Compose Android, Python FastAPI backend. Chat is the front door.
- Weather values come only from validated provider data, never an LLM or invented fallback.
- Official warnings take precedence; unavailable warnings never mean no warnings.
- Room is the Android source of truth. Display cached timestamps and offline limitations.
- Preserve four provider interfaces, multilingual UI, voice input and playback, and accessibility.
- Large labelled controls, scalable text, plain language, light/dark/system theme.
- No secrets in Android. No demo mode (user override of master spec sections 68–69).
- Test before claiming success. Track unimplemented requirements and environment blockers honestly.
