# Gemini integration and tuning

Gemini is optional and backend-only. The deterministic chat pipeline resolves intent, location, and time, calls typed weather tools, and constructs a verified draft before Gemini may improve wording. Structured output is validated against the draft numbers and warning meaning; transport, schema, or semantic failure returns the deterministic draft.

No fine-tuned model is shipped. Tuning requires a reviewed multilingual evaluation dataset with verified tool traces, difficult warning cases, and hallucination tests. Accuracy must beat the deterministic baseline before deployment. Missing credentials are an external blocker, never replaced with simulated output.
