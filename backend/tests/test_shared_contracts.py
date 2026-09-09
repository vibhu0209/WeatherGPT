import json
from pathlib import Path
from app.models import Location, Point

ROOT=Path(__file__).parents[2]

def test_shared_bundle_contract_matches_backend_models():
    data=json.loads((ROOT/'contracts'/'weather_bundle.json').read_text(encoding='utf-8'))
    location=Location.model_validate(data['location'])
    point=Point.model_validate(data['hourly'][0])
    assert location.timezone=='Asia/Kolkata'
    assert point.weather_code==61
    assert data['confidence']['calibrated_probability'] is False
    assert data['official_alerts'][0]['classification']=='official'

def test_shared_error_contract_has_required_envelope():
    data=json.loads((ROOT/'contracts'/'error.json').read_text(encoding='utf-8'))
    assert set(data)=={'code','message','retryable','request_id'}
    assert isinstance(data['retryable'],bool) and data['request_id']
