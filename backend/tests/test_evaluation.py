from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.evaluation import ForecastSample, evaluate


NOW=datetime(2026,9,8,tzinfo=timezone.utc)


def sample(predicted,observed,variable='temperature',available=True):
    return ForecastSample(provider='provider-a',model_family='model-a',variable=variable,issued_at=NOW,valid_at=NOW,
        predicted=predicted,observed=observed,available=available,observation_source='IMD station',latency_ms=100)


def test_evaluation_calculates_error_bias_availability_and_latency():
    result=evaluate([sample(30,28),sample(29,30),sample(0,0,available=False)])['groups'][0]
    assert result['mae']==1.5 and result['bias']==0.5
    assert result['availability']==pytest.approx(2/3,abs=0.0001) and result['mean_latency_ms']==100


def test_rain_brier_score_uses_probability_and_occurrence():
    result=evaluate([sample(.8,1,'rain_probability'),sample(.4,0,'rain_probability')])['groups'][0]
    assert result['brier_score']==0.1


def test_invalid_probability_and_naive_time_are_rejected():
    with pytest.raises(ValidationError): sample(80,1,'rain_probability')
    with pytest.raises(ValidationError): ForecastSample(provider='x',model_family='x',variable='temperature',issued_at=datetime.now(),valid_at=NOW,predicted=1,observed=1,observation_source='x')
