"""In-process counters for cache and paid-API use. Never stores locations or chat text."""
from __future__ import annotations

from collections import defaultdict


class Counters:
    def __init__(self) -> None:
        self._values: dict[str, int] = defaultdict(int)

    def inc(self, name: str, amount: int = 1) -> None:
        self._values[name] += amount

    def snapshot(self) -> dict[str, int]:
        return dict(self._values)

    def reset(self) -> None:
        self._values.clear()


metrics = Counters()
