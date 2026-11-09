"""Fail-closed UDP emergency-stop sender for an explicitly enabled bench/hardware session.

This module is NOT started by the simulation dashboard. A hardware runtime must
opt in, and the XIAO firmware must implement the ESTOP flag and local watchdog.
"""
from __future__ import annotations

from threading import Event, RLock, Thread
from typing import Protocol

from railroad.transport.udp import Broadcaster, Command
from railroad.transport.usb import ControllerRegistry

ESTOP_FLAG = 0x80
REARM_FLAG = 0x40
ALL_TRAINS = 0xFF
DEFAULT_PERIOD_S = 0.100


class Sender(Protocol):
    def send(self, command: Command) -> None: ...


class EStopFanout:
    """Send normal commands over UDP and E-Stop text to registered USB ports."""
    def __init__(self, udp_sender: Sender, controllers: ControllerRegistry | None = None):
        self.udp_sender = udp_sender
        self.controllers = controllers or ControllerRegistry()
        self._sequence = 0

    def _next_sequence(self) -> int:
        self._sequence = (self._sequence + 1) & 0xFFFF
        return self._sequence

    def send(self, command: Command) -> None:
        errors = []
        try:
            self.udp_sender.send(command)
        except Exception as exc:
            errors.append(exc)
        if command.flags & ESTOP_FLAG:
            self.controllers.set_estop_active(True)
            try:
                self.controllers.send_estop()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise OSError("E-Stop transport delivery incomplete") from errors[0]

    def rearm(self) -> None:
        self.udp_sender.send(Command(ALL_TRAINS, self._next_sequence(), 0, flags=REARM_FLAG))
        self.controllers.rearm_all()
        self.controllers.set_estop_active(False)

    def close(self) -> None:
        close = getattr(self.udp_sender, "close", None)
        if close:
            close()
        self.controllers.close()


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
            except Exception as exc:
                # Any transport can fail; stay latched and retry independently.
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
            setter = getattr(self._sender, "controllers", None)
            if setter is not None:
                setter.set_estop_active(False)
            self._wake.set()

    def rearm(self) -> None:
        """Explicit second step after clear; caller must verify safety first."""
        with self._lock:
            if self._closed or self._estop:
                raise RuntimeError("cannot rearm with E-Stop active or sender closed")
            if self._last_error:
                raise RuntimeError("unresolved broadcast error")
            # Explicit zero-speed handshake. Normal zero heartbeats never
            # clear a controller's local watchdog/E-Stop latch.
            try:
                rearm = getattr(self._sender, "rearm", None)
                if rearm:
                    rearm()
                else:
                    self._sender.send(self._next(estop=False, flags=REARM_FLAG))
            except Exception as exc:
                self._last_error = exc
                raise RuntimeError("rearm handshake delivery failed") from exc
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
        close = getattr(self._sender, "close", None)
        if close:
            close()


def create_bench_sender(*, enable_network: bool = False, controllers: ControllerRegistry | None = None) -> EmergencyStop:
    """Explicit opt-in only. Never call from simulation runtime."""
    if not enable_network:
        raise RuntimeError("hardware network broadcasts are disabled by default")
    return EmergencyStop(EStopFanout(Broadcaster(), controllers))
