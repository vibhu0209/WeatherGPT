import json
from pathlib import Path

from app.chat import answer
from app.models import ChatRequest, Location


CASES=json.loads((Path(__file__).parents[1]/'evaluation'/'ai_cases.json').read_text(encoding='utf-8'))


def test_ai_evaluation_dataset_covers_languages_intents_and_attacks():
    assert {case['language'] for case in CASES}=={'en','hi','bn','te','mr','ta','gu','kn','ml','pa','or'}
    required={'general_weather','farming','fishing','construction','tourism','transport','alerts','climate','adversarial'}
    assert required <= {case['intent'] for case in CASES}
    assert sum(case['intent']=='adversarial' for case in CASES)>=3
    assert all(case.get('must_not_invent') is True for case in CASES)
    assert any(case.get('turn')==2 and case.get('prior_case') for case in CASES)


def test_evaluation_attacks_do_not_create_unsupplied_values_or_warnings():
    location=Location(name='Delhi',latitude=28.6,longitude=77.2)
    bundle={'hourly':[],'is_stale':False,'retrieved_at':'2026-09-09T12:00:00Z','sources':[],
        'agreement':'unavailable','official_status':'unavailable','official_alerts':[]}
    for case in (item for item in CASES if item['intent']=='adversarial'):
        result=answer(ChatRequest(text=case['text'],location=location),bundle)['answer'].lower()
        for value in case.get('forbidden_values',[]): assert value not in result
        for claim in case.get('forbidden_claims',[]): assert claim not in result
        assert 'official warning availability is unknown' not in result or 'red cyclone' not in result
