# Weather fusion

Adapters normalize values to Celsius, millimetres, metres per second, percentages, UTC timestamps, and WMO-style weather codes. Fusion aligns points by UTC time, rejects stale or invalid values, and excludes duplicate model families before combining independent sources.

Continuous values use a median. Wind direction uses circular statistics. Weather codes are categorical and become unavailable on disagreement instead of being averaged. OpenWeather three-hour precipitation is excluded from one-hour totals.

Responses include sources, disagreement reasons, and an explainable coverage/agreement score. The score is uncalibrated and is not a probability or safety guarantee. Weights remain equal until representative observations justify a change.
