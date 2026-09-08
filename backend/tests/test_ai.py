from app.ai import validate_polish


def test_polish_accepts_plain_rewording_with_same_facts():
    assert validate_polish('Temperature: 28 to 31°C. Rain chance: 40%.','It will be 28 to 31°C, with a 40% rain chance.')


def test_polish_rejects_invented_weather_number():
    assert not validate_polish('Temperature: 28 to 31°C.','Temperature: 28 to 31°C. Wind: 12 km/h.')

def test_polish_rejects_dropped_weather_number():
    assert not validate_polish('Temperature: 28 to 31°C.','It will be 28°C.')


def test_polish_rejects_false_no_warning_claim():
    assert not validate_polish('Official warnings are unavailable.','There are no weather warnings.')
