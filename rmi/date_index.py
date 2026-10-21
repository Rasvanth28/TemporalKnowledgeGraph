"""Learned index over the real event timeline: date -> the events on it.

Real events share dates (the live graph has ~26k events on ~560 days), while the RMI needs sorted,
unique keys. So the RMI learns the distinct days, and an offsets array maps day ``i`` to its contiguous
run of events (sorted by date, then id), the same layout as a CSR index. That answers the questions the
graph's B+ tree ``event_date`` index answers: events on a day, and events in a date range.

Range ends are usually days the model never saw. ``RMIModel.lower_bound`` verifies each guess; when it
cannot, the injected fallback answers (``bisect`` in process, or Neo4j via ``rmi.live``), so every answer
is correct and the fallback rate is measurable.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np

from rmi.config import RMIConfig
from rmi.train import train_rmi

LowerBound = Callable[[int], int]


def bisect_lower_bound(days: np.ndarray) -> LowerBound:
    values = [int(day) for day in days]
    return lambda key: bisect_left(values, int(key))


@dataclass
class DateIndex:
    days: np.ndarray        # sorted unique date keys (days since 1970-01-01)
    offsets: np.ndarray     # events of days[i] are event_ids[offsets[i]:offsets[i + 1]]
    event_ids: list[str]    # sorted by (date_key, event_id)
    model: object           # trained RMIModel over ``days``
    fallback: LowerBound
    fallbacks: int = field(default=0)

    @classmethod
    def build(cls, rows: Iterable[tuple[int, str]], config: RMIConfig | None = None,
              fallback: Callable[[np.ndarray], LowerBound] = bisect_lower_bound) -> "DateIndex":
        """Index ``(date_key, event_id)`` rows; ``fallback`` is built over the same days."""

        ordered = sorted((int(key), str(event_id)) for key, event_id in rows)
        if not ordered:
            raise ValueError("cannot index an empty event set")
        keys = np.fromiter((key for key, _ in ordered), dtype=np.int64, count=len(ordered))
        days, starts = np.unique(keys, return_index=True)
        offsets = np.append(starts, len(ordered)).astype(np.int64)
        return cls(days, offsets, [event_id for _, event_id in ordered], train_rmi(days, config), fallback(days))

    def _lower(self, key: int) -> int:
        result = self.model.lower_bound(key)
        if result.used_fallback:
            self.fallbacks += 1
            return self.fallback(key)
        return int(result.index)

    def span(self, start: int, end: int) -> tuple[int, int]:
        """Event positions ``[lo, hi)`` dated ``start..end`` inclusive."""

        if end < start:
            return 0, 0
        return int(self.offsets[self._lower(start)]), int(self.offsets[self._lower(end + 1)])

    def between(self, start: int, end: int) -> list[str]:
        lo, hi = self.span(start, end)
        return self.event_ids[lo:hi]

    def on(self, day: int) -> list[str]:
        return self.between(day, day)

    def summary(self) -> dict[str, object]:
        return {"events": len(self.event_ids), "days": len(self.days), **self.model.summary()}
