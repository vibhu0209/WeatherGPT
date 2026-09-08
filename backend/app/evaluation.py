from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import sqrt
from pydantic import BaseModel, Field, model_validator


class ForecastSample(BaseModel):
    provider: str
    model_family: str
    variable: str
    issued_at: datetime
    valid_at: datetime
    predicted: float
    observed: float
    observation_source: str
    available: bool = True
    latency_ms: float | None = Field(default=None, ge=0)
    @model_validator(mode='after')
    def valid(self):
        if self.issued_at.tzinfo is None or self.valid_at.tzinfo is None:
            raise ValueError('Evaluation timestamps must include timezone')
        if self.variable == 'rain_probability' and not 0 <= self.predicted <= 1:
            raise ValueError('Rain probability must be between zero and one')
        if self.variable == 'rain_probability' and self.observed not in (0, 1):
            raise ValueError('Observed rain occurrence must be zero or one')
        return self


def evaluate(samples: list[ForecastSample]) -> dict:
    grouped = defaultdict(list)
    for sample in samples:
        grouped[(sample.provider, sample.variable)].append(sample)
    output = []
    for (provider, variable), rows in sorted(grouped.items()):
        errors = [row.predicted-row.observed for row in rows if row.available]
        latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
        result = {'provider':provider,'variable':variable,'sample_count':len(rows),
            'available_count':sum(row.available for row in rows),
            'availability':round(sum(row.available for row in rows)/len(rows),4),
            'mean_latency_ms':round(sum(latencies)/len(latencies),1) if latencies else None,
            'mae':round(sum(abs(value) for value in errors)/len(errors),3) if errors else None,
            'bias':round(sum(errors)/len(errors),3) if errors else None,
            'rmse':round(sqrt(sum(value*value for value in errors)/len(errors)),3) if errors else None}
        result['brier_score'] = round(sum(value*value for value in errors)/len(errors),4) if variable=='rain_probability' and errors else None
        output.append(result)
    return {'groups':output,'weighting_applied':False,
        'warning':'Metrics require a representative matched observation archive before they may influence fusion weights.'}
