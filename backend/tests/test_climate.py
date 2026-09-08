from datetime import date, timedelta

import pytest

from app.climate import calculate_summary


def payload(start: date, end: date, value):
    dates, values = [], []
    day = start
    while day <= end:
        dates.append(day.isoformat())
        values.append(value(day))
        day += timedelta(days=1)
    return {"daily": {"time": dates, "temperature_2m_mean": values}}


def test_temperature_trend_and_coverage_are_deterministic():
    data = payload(date(2023, 1, 1), date(2025, 12, 31), lambda day: 20 + (day.year - 2023))
    result = calculate_summary(data, "temperature", 2023, 2025)
    assert result["trend_per_decade"] == 10
    assert result["coverage"] == 1
    assert result["source_type"] == "REANALYSIS"
    assert result["latest_anomaly"] == 1.5
    assert "does not attribute" in result["limitations"]


def test_incomplete_year_is_not_used_for_trend():
    data = payload(date(2023, 1, 1), date(2025, 12, 31), lambda day: None if day.year == 2024 else 20 + day.year - 2023)
    result = calculate_summary(data, "temperature", 2023, 2025)
    assert result["annual"][1]["usable"] is False
    assert result["annual"][1]["value"] is None
    assert result["trend_per_decade"] == 10


def test_insufficient_climate_data_is_rejected():
    data = payload(date(2023, 1, 1), date(2024, 12, 31), lambda day: 20 if day.year == 2023 else None)
    with pytest.raises(ValueError, match="Insufficient"):
        calculate_summary(data, "temperature", 2023, 2024)


def test_mismatched_provider_arrays_are_rejected():
    with pytest.raises(ValueError, match="lengths differ"):
        calculate_summary({"daily":{"time":["2024-01-01"],"temperature_2m_mean":[]}}, "temperature", 2023, 2024)
