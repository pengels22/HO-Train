"""Locomotive command transport with dispatcher stop and explicit motion authorization.

Wire flag 0x80 is kept for compatibility with existing locomotive firmware.
It is not a physical emergency-stop system.
"""
from __future__ import annotations

from threading import Event, RLock, Thread
from typing import Protocol
import time

from railroad.transport.udp import Broadcaster, Command
from railroad.transport.usb import ControllerRegistry

GLOBAL_STOP_FLAG = 0x80
REARM_FLAG = 0x40
ALL_TRAINS = 0xFF
DEFAULT_PERIOD_S = 0.100


class Sender(Protocol):
    def send(self, command: Command) -> None: ...


class LocomotiveStopFanout:
    """Send normal commands over UDP and dispatcher stop text to registered USB ports."""
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
        if command.flags & GLOBAL_STOP_FLAG:
            self.controllers.set_stop_active(True)
            try:
                self.controllers.send_stop()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise OSError("dispatcher stop transport delivery incomplete") from errors[0]

    def rearm(self, transaction: str | None = None) -> None:
        transaction = transaction or f"rearm-{time.monotonic_ns()}"
        send_rearm = getattr(self.udp_sender, "send_rearm", None)
        if send_rearm:
            send_rearm(transaction)
        else:
            # Compatibility path for deterministic simulation/test senders.
            self.udp_sender.send(Command(ALL_TRAINS, self._next_sequence(), 0, flags=REARM_FLAG))
        # Accessory faults remain local. A disconnected/faulted tipper or
        # turntable must not prevent independent locomotive rearm.
        # Accessories keep their own E-stop latch until explicitly rearmed
        # through their validated local workflow.
        self.controllers.set_stop_active(False)

    def close(self) -> None:
        close = getattr(self.udp_sender, "close", None)
        if close:
            close()
        self.controllers.close()


class LocomotiveCommandTransport:
    """Own the command stream so ordinary throttle commands cannot bypass a latch.

    Starts DISARMED; only explicit rearm permits motion. An dispatcher stop sends an
    immediate zero command and continues at 100 ms until cleared. Clearing
    keeps the system DISARMED, with all trains stopped.
    """

    def __init__(self, sender: Sender, period_s: float = DEFAULT_PERIOD_S, *, start_armed: bool = False):
        if period_s <= 0:
            raise ValueError("period_s must be positive")
        self._sender = sender
        self._period_s = period_s
        self._lock = RLock()
        self._wake = Event()
        self._closed = False
        self._stopped = False
        self._armed = start_armed
        self._sequence = 0
        self._last_error: Exception | None = None
        self._thread = Thread(target=self._broadcast_loop, name="ho-stopped", daemon=True)
        self._thread.start()

    @property
    def active(self) -> bool:
        with self._lock:
            return self._stopped

    @property
    def armed(self) -> bool:
        with self._lock:
            return self._armed and not self._stopped

    @property
    def last_error(self) -> Exception | None:
        with self._lock:
            return self._last_error

    def _next(self, *, stopped: bool, train_id: int = ALL_TRAINS,
              speed: int = 0, target: int = 0, flags: int = 0) -> Command:
        self._sequence = (self._sequence + 1) & 0xFFFF
        return Command(
            train_id=train_id, sequence=self._sequence, speed=0 if stopped else speed,
            target=0 if stopped else target, flags=GLOBAL_STOP_FLAG if stopped else flags,
        )

    def _send_stop(self) -> None:
        # Lock is held through send: no concurrent throttle packet can race
        # across the dispatcher stop boundary.
        with self._lock:
            if not self._stopped or self._closed:
                return
            try:
                self._sender.send(self._next(stopped=True))
                self._last_error = None
            except Exception as exc:
                # Any transport can fail; stay latched and retry independently.
                self._last_error = exc

    def activate(self) -> None:
        """Immediately broadcast STOP; keep broadcasting until clear()."""
        with self._lock:
            if self._closed:
                raise RuntimeError("dispatcher stop sender is closed")
            self._stopped = True
            self._armed = False
            self._send_stop()
            self._wake.set()

    def clear(self) -> None:
        """Stop dispatcher stop repetition; NEVER resume prior throttle commands."""
        with self._lock:
            self._stopped = False
            self._armed = False
            setter = getattr(self._sender, "controllers", None)
            if setter is not None:
                setter.set_stop_active(False)
            self._wake.set()

    def rearm(self, transaction: str | None = None) -> None:
        """Explicit second step after clear; caller must verify safety first."""
        with self._lock:
            if self._closed or self._stopped:
                raise RuntimeError("cannot rearm with dispatcher stop active or sender closed")
            if self._last_error:
                raise RuntimeError("unresolved broadcast error")
            # Explicit zero-speed handshake. Normal zero heartbeats never
            # clear a controller's local watchdog/dispatcher stop latch.
            try:
                rearm = getattr(self._sender, "rearm", None)
                if rearm:
                    rearm(transaction)
                else:
                    self._sender.send(self._next(stopped=False, flags=REARM_FLAG))
            except Exception as exc:
                self._last_error = exc
                raise RuntimeError("rearm handshake delivery failed") from exc
            self._armed = True

    def send_motion(self, train_id: int, speed: int, target: int = 0, flags: int = 0) -> None:
        """Sole path for motion packets in the hardware command runtime."""
        with self._lock:
            if self._closed or self._stopped or not self._armed:
                raise RuntimeError("motion command blocked: dispatcher stop or disarmed")
            if flags & GLOBAL_STOP_FLAG or train_id == ALL_TRAINS:
                raise ValueError("reserved dispatcher stop flag or broadcast train ID")
            self._sender.send(self._next(stopped=False, train_id=train_id,
                                          speed=speed, target=target, flags=flags))

    def _broadcast_loop(self) -> None:
        while True:
            # The event lets clear()/activate() interrupt the wait.
            self._wake.wait(self._period_s)
            self._wake.clear()
            with self._lock:
                if self._closed:
                    return
                active = self._stopped
            if active:
                self._send_stop()

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


def create_bench_sender(*, enable_network: bool = False, controllers: ControllerRegistry | None = None, start_armed: bool = False) -> LocomotiveCommandTransport:
    """Explicit opt-in only. Never call from simulation runtime."""
    if not enable_network:
        raise RuntimeError("hardware network broadcasts are disabled by default")
    return LocomotiveCommandTransport(LocomotiveStopFanout(Broadcaster(), controllers), start_armed=start_armed)
