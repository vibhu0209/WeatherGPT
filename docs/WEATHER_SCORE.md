# Weather Score

WeatherGPT computes deterministic planning guidance from the next 24 hours of validated forecast data. Heat, rain, wind, and visibility components have explicit thresholds. Farming, outdoor, and general profiles change sensitivities and produce plain-language limiting factors.

The fishing profile does not convert land weather into a marine safety score. It directs users to official IMD or INCOIS guidance and the separate validated marine path. The score is always secondary to official warnings and is labelled as planning guidance.

Tests cover bounds, missing data, and profile differences. Thresholds need field evaluation before production use.
