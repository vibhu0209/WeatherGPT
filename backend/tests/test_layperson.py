from app.layperson import format_layperson_answer


def test_layperson_formats_rain_dump():
    raw = (
        'Maybe — rain is possible. Keep outdoor plans flexible.\n\n'
        'Delhi\n\n'
        'Rain chance peaks around 50% (supporting detail).\n\n'
        'Temperature: 24.3 to 38.2°C.\n\n'
        'If an IMD warning is active for your area, follow that first.\n\n'
        'The connected official service reports no active warning at this time.'
    )
    out = format_layperson_answer(raw)
    assert out.startswith('Maybe — rain is possible')
    assert 'supporting detail' not in out.lower()
    assert 'supporting reading' not in out.lower()
    assert 'connected official service' not in out.lower()
    assert '50%' in out or 'rain' in out.lower()
    assert '24.3' in out and '38.2' in out
    assert 'Delhi' not in out or 'rain' in out.lower()
    assert out.count('\n\n') <= 4


def test_layperson_formats_score_dump():
    raw = (
        'Yes — weather-wise, conditions look reasonably suitable for going outside.\n\n'
        'Choose the better weather window shown below and check official warnings before leaving.\n\n'
        'Supporting reading: 89/100 (Good conditions). This score is guidance for your plan.\n\n'
        'Models differ a little on timing — the recommended window still stands.'
    )
    out = format_layperson_answer(raw)
    assert out.startswith('Yes —')
    assert '89/100' not in out
    assert 'models differ' not in out.lower()
    assert 'Choose the better weather window' in out
