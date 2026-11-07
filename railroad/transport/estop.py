"""Fail-closed UDP emergency-stop sender for an explicitly enabled bench/hardware session.

This module is NOT started by the simulation dashboard. A hardware runtime must
opt in, and the XIAO firmware must implement the ESTOP flag and local watchdog.
"""
from __future__ import annotations

from threading import Event, RLock, Thread
from typing import Protocol

from railroad.transport.udp import Broadcaster, Command

ESTOP_FLAG = 0x80
ALL_TRAINS = 0xFF
DEFAULT_PERIOD_S = 0.100


class Sender(Protocol):
    def send(self, command: Command) -> None: ...


class EmergencyStop:
    """Own the command stream so ordinary throttle commands cannot bypass a latch.

    Starts DISARMED; only explicit rearm permits motion. An E-Stop sends an
    immediate zero command and continues at 100 ms until cleared. Clearing
    keeps the system DISARMED, with all trains stopped.
    """

    def __init__(self, sender: Sender, period_s: float = DEFAULT_PERIOD_S):
        if period_s <= 0:
            raise ValueError("period_s must be positive")
        self._sender = sender
        self._period_s = period_s
        self._lock = RLock()
        self._wake = Event()
        self._closed = False
        self._estop = False
        self._armed = False
        self._sequence = 0
        self._last_error: Exception | None = None
        self._thread = Thread(target=self._broadcast_loop, name="ho-estop", daemon=True)
        self._thread.start()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._estop

    @property
    def armed(self) -> bool:
        with self._lock:
            return self._armed and not self._estop

    @property
    def last_error(self) -> Exception | None:
        with self._lock:
            return self._last_error

    def _next(self, *, estop: bool, train_id: int = ALL_TRAINS,
              speed: int = 0, target: int = 0, flags: int = 0) -> Command:
        self._sequence = (self._sequence + 1) & 0xFFFF
        return Command(
            train_id=train_id, sequence=self._sequence, speed=0 if estop else speed,
            target=0 if estop else target, flags=ESTOP_FLAG if estop else flags,
        )

    def _send_estop(self) -> None:
        # Lock is held through send: no concurrent throttle packet can race
        # across the E-Stop boundary.
        with self._lock:
            if not self._estop or self._closed:
                return
            try:
                self._sender.send(self._next(estop=True))
                self._last_error = None
            except OSError as exc:
                # UDP can fail; stay latched and retry on every cycle.
                self._last_error = exc

    def activate(self) -> None:
        """Immediately broadcast ESTOP; keep broadcasting until clear()."""
        with self._lock:
            if self._closed:
                raise RuntimeError("E-Stop sender is closed")
            self._estop = True
            self._armed = False
            self._send_estop()
            self._wake.set()

    def clear(self) -> None:
        """Stop E-Stop repetition; NEVER resume prior throttle commands."""
        with self._lock:
            self._estop = False
            self._armed = False
            self._wake.set()

    def rearm(self) -> None:
        """Explicit second step after clear; caller must verify safety first."""
        with self._lock:
            if self._closed or self._estop:
                raise RuntimeError("cannot rearm with E-Stop active or sender closed")
            if self._last_error:
                raise RuntimeError("unresolved broadcast error")
            self._armed = True

    def send_motion(self, train_id: int, speed: int, target: int = 0, flags: int = 0) -> None:
        """Sole path for motion packets in the hardware command runtime."""
        with self._lock:
            if self._closed or self._estop or not self._armed:
                raise RuntimeError("motion command blocked: E-Stop or disarmed")
            if flags & ESTOP_FLAG or train_id == ALL_TRAINS:
                raise ValueError("reserved E-Stop flag or broadcast train ID")
            self._sender.send(self._next(estop=False, train_id=train_id,
                                          speed=speed, target=target, flags=flags))

    def _broadcast_loop(self) -> None:
        while True:
            # The event lets clear()/activate() interrupt the wait.
            self._wake.wait(self._period_s)
            self._wake.clear()
            with self._lock:
                if self._closed:
                    return
                active = self._estop
            if active:
                self._send_estop()

    def shutdown(self) -> None:
        """Stop the worker. A supervising service must handle hardware shutdown."""
        with self._lock:
            self._closed = True
            self._armed = False
            self._wake.set()
        self._thread.join(timeout=1.0)


def create_bench_sender(*, enable_network: bool = False) -> EmergencyStop:
    """Explicit opt-in only. Never call from simulation runtime."""
    if not enable_network:
        raise RuntimeError("hardware network broadcasts are disabled by default")
    return EmergencyStop(Broadcaster())
