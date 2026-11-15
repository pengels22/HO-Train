"""Stable reed-switch edge events; contact debounce is not pulse lockout."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReedState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class ReedEvent:
    sensor: str
    state: ReedState
    timestamp: float
    duration_s: float | None = None
    pulse_number: int = 0


class ReedDebouncer:
    def __init__(self, sensor: str, debounce_ms: int = 15):
        if debounce_ms < 0:
            raise ValueError("debounce_ms must be non-negative")
        self.sensor = sensor
        self.debounce_s = debounce_ms / 1000
        self.state = ReedState.OPEN
        self._candidate: ReedState | None = None
        self._candidate_at = 0.0
        self._closed_at: float | None = None
        self.pulses = 0

    def update(self, closed: bool, timestamp: float) -> list[ReedEvent]:
        candidate = ReedState.CLOSED if closed else ReedState.OPEN
        if candidate == self.state:
            self._candidate = None
            return []
        if self._candidate != candidate:
            self._candidate, self._candidate_at = candidate, timestamp
            return []
        if timestamp - self._candidate_at < self.debounce_s:
            return []
        self.state = candidate
        self._candidate = None
        if candidate is ReedState.CLOSED:
            self._closed_at = self._candidate_at
            return [ReedEvent(self.sensor, candidate, timestamp)]
        self.pulses += 1
        duration = None if self._closed_at is None else timestamp - self._closed_at
        self._closed_at = None
        return [ReedEvent(self.sensor, candidate, timestamp, duration, self.pulses)]
