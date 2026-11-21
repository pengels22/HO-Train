"""Debounced Mega reed callback reader, no USB side effects at import."""
from collections import deque
from dataclasses import dataclass
from threading import Lock
import time

from railroad.hardware.reed import ReedEvent, ReedState


@dataclass
class Contact:
    raw: bool | None = None
    last_change: float | None = None
    stable: bool | None = None
    closed_at: float | None = None
    pulses: int = 0


class MegaReedReader:
    """Queue raw Firmata digital callbacks; dispatch events only in poll()."""

    def __init__(self, board, pin_map, on_event, *, debounce_ms=15,
                 clock=time.monotonic, max_pending=4096):
        if len(pin_map) != 28 or len(set(pin_map.values())) != 28:
            raise ValueError("28 unique reed assignments required")
        if debounce_ms < 0 or max_pending < 1:
            raise ValueError("invalid debounce or queue limit")
        self.board = board
        self.pin_map = dict(pin_map)
        self.on_event = on_event
        self.debounce = debounce_ms / 1000
        self.clock = clock
        self.max_pending = max_pending
        self.contacts = {name: Contact() for name in pin_map.values()}
        self._queue = deque()
        self._lock = Lock()
        self._overflow = False
        self.started = False

    def _callback(self, name, value):
        if value is None:
            return
        if value not in (0, 1, False, True):
            raise ValueError("invalid reed digital level")
        with self._lock:
            if self._overflow:
                return
            if len(self._queue) >= self.max_pending:
                self._overflow = True
                return
            self._queue.append((self.clock(), name, not bool(value)))

    def start(self):
        if self.started:
            return
        if getattr(self.board, "board", None) is None:
            raise RuntimeError("Firmata Mega must be connected explicitly")
        for label, name in self.pin_map.items():
            if not label.startswith("D") or not 14 <= int(label[1:]) <= 41:
                raise ValueError("invalid reed pin: " + label)
            pin = self.board.pin(int(label[1:]), "u")
            pin.register_callback(lambda value, *args, name=name: self._callback(name, value))
            pin.enable_reporting()
        self.started = True

    def _settle(self, name, contact, moment, results):
        if contact.raw is None or contact.last_change is None:
            return
        if moment - contact.last_change < self.debounce or contact.raw == contact.stable:
            return
        if contact.stable is None:
            contact.stable = contact.raw
            if contact.stable:
                contact.closed_at = contact.last_change
            return
        contact.stable = contact.raw
        if contact.stable:
            contact.closed_at = contact.last_change
            results.append(ReedEvent(name, ReedState.CLOSED, moment))
        else:
            contact.pulses += 1
            duration = None if contact.closed_at is None else moment - contact.closed_at
            contact.closed_at = None
            results.append(ReedEvent(name, ReedState.OPEN, moment, duration, contact.pulses))

    def poll(self, *, now=None):
        if not self.started:
            raise RuntimeError("reed reader not started")
        with self._lock:
            if self._overflow:
                raise RuntimeError("reed callback overflow: car count no longer trusted")
            queued = list(self._queue)
            self._queue.clear()
        events = []
        for when, name, closed in queued:
            entry = self.contacts[name]
            self._settle(name, entry, when, events)
            if closed != entry.raw:
                entry.raw = closed
                entry.last_change = when
        when = self.clock() if now is None else now
        for name, entry in self.contacts.items():
            self._settle(name, entry, when, events)
        for event in events:
            self.on_event(event)
        return events

    def status(self):
        return {name: {"state": "UNKNOWN" if entry.stable is None else
                              "CLOSED" if entry.stable else "OPEN",
                       "pulse_number": entry.pulses}
                for name, entry in self.contacts.items()}
