# Optional Gemini supervised tuning pipeline

WeatherGPT currently uses grounded Gemini function calling, structured prompting, response validation and an evaluation dataset. This folder is reserved for **optional** supervised tuning on supported Google Cloud / enterprise Gemini platforms.

## What tuning may improve

- Intent classification and tool-selection behaviour
- Indian weather terminology and multilingual question understanding
- Occupation-specific phrasing and uncertainty communication
- Concise rural-friendly responses

## What tuning must never do

- Memorize current forecasts or warnings
- Replace validated weather tools
- Soften or override official warnings

## Prerequisites

- Google Cloud project with Gemini supervised tuning enabled
- Billing approval from the project owner
- `GEMINI_API_KEY` or service-account credentials with tuning permissions
- Exported training examples derived from `backend/evaluation/ai_cases.json` (intent and phrasing only, never live numbers)

## Suggested layout

```
backend/ai/tuning/
  datasets/          # Approved intent/phrasing examples without live weather values
  training/          # Tuning job configuration and launch scripts
  evaluation/        # Held-out evaluation prompts and scoring notes
  scripts/           # Helper scripts to prepare JSONL training files
  README.md          # This file
```

## Launch policy

Do **not** automatically launch a potentially chargeable tuning job. A human operator must review the dataset, confirm credentials, and explicitly approve any cloud training run.

If tuning is unavailable through the configured platform, WeatherGPT continues with system prompting, tool calling and validated structured grounding.
