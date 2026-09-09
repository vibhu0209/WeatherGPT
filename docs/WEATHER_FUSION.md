# Weather fusion

Adapters normalize values to Celsius, millimetres, metres per second, percentages, UTC timestamps, and WMO-style weather codes. Fusion aligns points by UTC time, rejects stale or invalid values, and excludes duplicate model families before combining independent sources.

Continuous values use a configured weighted median. Wind direction uses weighted circular statistics. Weather codes use weighted categorical voting and remain unavailable when the leading categories tie. OpenWeather three-hour precipitation is excluded from one-hour totals.

Responses include sources, disagreement reasons, and an explainable coverage/agreement score. The score is uncalibrated and is not a probability or safety guarantee. Initial configured weights remain equal until representative matched observations justify a reviewed change.
