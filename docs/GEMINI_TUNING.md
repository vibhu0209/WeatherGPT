# Gemini supervised tuning

WeatherGPT does **not** claim that system prompting equals fine-tuning.

## Required prototype AI (implemented)

- System prompt: `backend/ai/prompts/weather_assistant.md`
- Deterministic weather tools before any wording pass
- Structured Gemini polish with schema + `validate_polish`
- Fallback to verified draft when Gemini is disabled, rate-limited, or fails

Meteorological numbers always come from tools/fusion — never from model memory.

## Optional supervised tuning pipeline

Path: `backend/ai/tuning/`

Use only when Google Cloud / enterprise Gemini supervised tuning is available with explicit user approval for a chargeable job.

Intended dataset goals:

- Intent / tool selection for Indian weather questions
- Occupation phrasing
- Multilingual understanding
- Uncertainty communication
- Refusal of fabricated numbers

Do **not** train the model to memorize forecasts.

## Current status

`GEMINI_API_KEY` / `GEMINI_MODEL` are absent in the default local environment. Live polish and any cloud tuning job remain blocked until credentials and approval are provided.
