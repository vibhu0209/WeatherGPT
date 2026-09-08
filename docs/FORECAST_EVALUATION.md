# Forecast provider evaluation

The provider contract records stable provider and model-family identities so forecasts can later be compared with observations without mixing duplicate model output.

The planned evaluation store records the forecast issue time, valid time, provider, model family, location or station, predicted value, later observed value, observation authority, latency and provider availability. Metrics are temperature and wind mean absolute error and bias, rain Brier score when the provider supplies a probability, coverage, availability, and request latency. Metrics must be segmented by forecast horizon, season and region; a single national average is not enough for weighting.

No empirical accuracy weights are active yet because the repository does not have a representative archive of matched authoritative observations. Current fusion therefore uses an unweighted median per independent model family and describes its confidence score as uncalibrated. Any future weights require a documented evaluation window, minimum sample size, holdout validation, and a safe fallback when regional evidence is sparse.
