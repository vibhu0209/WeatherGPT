from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
import asyncio

import httpx

from .metrics import metrics
from .models import Location


def calculate_summary(payload: dict, metric: str, start_year: int, end_year: int) -> dict:
    daily = payload.get("daily", {})
    times = daily.get("time", [])
    field = "temperature_2m_mean" if metric == "temperature" else "precipitation_sum"
    raw_values = daily.get(field, [])
    if len(times) != len(raw_values):
        raise ValueError("Historical time and value lengths differ")

    grouped: dict[int, list[float]] = defaultdict(list)
    expected: dict[int, int] = {}
    for year in range(start_year, end_year + 1):
        expected[year] = (date(year + 1, 1, 1) - date(year, 1, 1)).days
    for raw_date, value in zip(times, raw_values):
        if value is None:
            continue
        day = date.fromisoformat(raw_date)
        if start_year <= day.year <= end_year:
            grouped[day.year].append(float(value))

    annual = []
    for year in range(start_year, end_year + 1):
        values = grouped.get(year, [])
        completeness = len(values) / expected[year]
        statistic = mean(values) if metric == "temperature" and values else sum(values) if values else None
        annual.append({
            "year": year,
            "value": round(statistic, 2) if statistic is not None else None,
            "unit": "°C" if metric == "temperature" else "mm",
            "days_present": len(values),
            "completeness": round(completeness, 4),
            "usable": completeness >= 0.90,
        })

    usable = [row for row in annual if row["usable"] and row["value"] is not None]
    if len(usable) < 2:
        raise ValueError("Insufficient complete years for a trend")
    xs = [row["year"] for row in usable]
    ys = [row["value"] for row in usable]
    x_mean, y_mean = mean(xs), mean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    baseline = mean(ys[:-1]) if len(ys) > 2 else mean(ys)
    latest = usable[-1]
    return {
        "metric": metric,
        "period": {"start_year": start_year, "end_year": end_year},
        "annual": annual,
        "trend_per_decade": round(slope * 10, 2),
        "latest_anomaly": round(latest["value"] - baseline, 2),
        "latest_year": latest["year"],
        "coverage": round(sum(row["days_present"] for row in annual) / sum(expected.values()), 4),
        "method": "OLS trend across annual mean temperature" if metric == "temperature" else "OLS trend across annual precipitation totals",
        "source": "Open-Meteo Historical Weather API / ERA5",
        "source_type": "REANALYSIS",
        "model": "ERA5",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limitations": "Reanalysis represents a model grid cell and may differ from a nearby weather station. Trend does not attribute causes.",
    }


class ClimateService:
    def __init__(self):
        self.cache: dict[tuple, tuple[datetime, dict]] = {}
        self._inflight: dict[tuple, asyncio.Future] = {}

    async def summary(self, location: Location, metric: str, years: int) -> dict:
        if metric not in {"temperature", "rainfall"}:
            raise ValueError("Unsupported climate metric")
        end_year = date.today().year - 1
        start_year = end_year - years + 1
        key = (round(location.latitude, 3), round(location.longitude, 3), metric, years)
        cached = self.cache.get(key)
        now = datetime.now(timezone.utc)
        if cached and now - cached[0] < timedelta(days=7):
            metrics.inc('climate_cache_hit')
            payload = dict(cached[1])
            payload['location'] = location.model_dump()
            return payload
        existing = self._inflight.get(key)
        if existing is not None:
            return await existing
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        future.add_done_callback(lambda done: done.cancelled() or done.exception())
        self._inflight[key] = future
        try:
            result = await self._fetch(location, metric, years, start_year, end_year)
            self.cache[key] = (now, result)
            metrics.inc('climate_cache_miss')
            if len(self.cache) > 64:
                self.cache.pop(next(iter(self.cache)))
            if not future.done():
                future.set_result(result)
            return result
        except Exception as error:
            if not future.done():
                future.set_exception(error)
            raise
        finally:
            self._inflight.pop(key, None)

    async def _fetch(self, location: Location, metric: str, years: int, start_year: int, end_year: int) -> dict:
        daily = "temperature_2m_mean" if metric == "temperature" else "precipitation_sum"
        async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
            response = await client.get("https://archive-api.open-meteo.com/v1/archive", params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "start_date": f"{start_year}-01-01",
                "end_date": f"{end_year}-12-31",
                "daily": daily,
                "timezone": location.timezone,
                "models": "era5",
            })
            response.raise_for_status()
        metrics.inc('provider_http')
        result = calculate_summary(response.json(), metric, start_year, end_year)
        result["location"] = location.model_dump()
        return result


climate_service = ClimateService()
