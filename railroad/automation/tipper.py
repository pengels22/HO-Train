from enum import Enum
from typing import Protocol
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from itertools import count

class TipperState(str, Enum):
    IDLE="IDLE"; LOADING="LOADING"; ROTATING="ROTATING"; RETURNING="RETURNING"; UNLOADING="UNLOADING"; FAULT="FAULT"

class TipperHardware(Protocol):
    """Allow-listed interface supplied by the validated tipper controller."""
    def stop_motor(self) -> None: ...
    def set_decoupler(self, enabled: bool) -> None: ...
    def rearm(self) -> None: ...

class TipperSerialController:
    """Allow-listed newline protocol for a future validated tipper board."""
    def __init__(self, port, response_timeout_s: float = 0.1):
        self.port = port
        self.response_timeout_s = response_timeout_s
        self.last_status: dict | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ho-tipper")
        self._transactions = count(1)
        self.communication_fault = False

    def reconnect(self, port=None) -> None:
        if port is not None: self.port = port
        self.communication_fault = False

    def command(self, name: str) -> str:
        if name not in {"ESTOP", "STOP", "STATUS", "REARM"}:
            raise ValueError("unsupported tipper command")
        if self.communication_fault and name != "ESTOP":
            raise RuntimeError("tipper communication fault requires reconnection")
        transaction = f"tipper-{next(self._transactions)}"
        future = self._executor.submit(self._exchange, name, transaction)
        try:
            reply = future.result(timeout=self.response_timeout_s)
        except TimeoutError as exc:
            self.communication_fault = True
            future.cancel(); self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ho-tipper")
            raise TimeoutError(f"tipper {name} acknowledgement timed out") from exc
        if reply.startswith("{"):
            try: self.last_status = json.loads(reply)
            except json.JSONDecodeError as exc: raise RuntimeError("malformed tipper status") from exc
            if self.last_status.get("transaction") != transaction:
                self.communication_fault = True
                raise RuntimeError("stale tipper transaction response")
        return reply

    def _exchange(self, name: str, transaction: str) -> str:
        self.port.write((json.dumps({"controller": "tipper", "command": name, "transaction": transaction}, separators=(",", ":")) + "\n").encode("ascii"))
        return self.port.readline().decode("ascii", errors="replace").strip()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def stop_motor(self) -> None:
        reply = self.command("ESTOP")
        confirmed = self.last_status is not None and self.last_status.get("motor") is False and self.last_status.get("decoupler") is False
        if not confirmed and reply != "OK ESTOP motor=off decoupler=off":
            raise RuntimeError("tipper controller did not confirm motor-off")

    def set_decoupler(self, enabled: bool) -> None:
        if enabled:
            raise RuntimeError("tipper decoupler protocol is not configured")
        if self.last_status is not None and self.last_status.get("decoupler", False):
            raise RuntimeError("tipper controller did not confirm decoupler-off")

    def rearm(self) -> None:
        response = self.command("REARM")
        if not response.startswith("OK"):
            raise RuntimeError("tipper controller rejected REARM: " + response)

class SafeTipperAdapter:
    """Hardware boundary; no GPIO, serial, or board assumptions are made."""
    def __init__(self, hardware: TipperHardware | None = None):
        self.hardware = hardware
        # A simulation has no output device to energize; a real adapter starts
        # disarmed until its controller performs the explicit rearm sequence.
        self.estop_latched = hardware is not None
        self.communication_fault = False
        self.last_error: str | None = None

    def stop(self) -> None:
        self.estop_latched = True
        self.last_error = None
        if self.hardware is None:
            return
        try:
            self.hardware.stop_motor()
            self.hardware.set_decoupler(False)
        except Exception as exc:
            self.last_error = str(exc)
            raise

    def communication_lost(self) -> None:
        self.communication_fault = True
        self.stop()

    def rearm(self) -> None:
        if self.communication_fault:
            raise RuntimeError("tipper communication fault remains active")
        if self.hardware is not None:
            self.hardware.rearm()
        self.estop_latched = False

class Tipper:
    def __init__(self, hardware: TipperHardware | None = None):
        self.state = TipperState.IDLE
        self.fault: str | None = None
        self.direction = 0
        self.adapter = SafeTipperAdapter(hardware)

    def emergency_stop(self) -> None:
        self.adapter.stop()
        self.direction = 0
        self.state = TipperState.FAULT
        self.fault = "E-Stop active"

    def rearm(self, home: bool, track_clear: bool) -> None:
        if not (home and track_clear) or self.fault:
            raise RuntimeError("tipper requires home, track-clear, and fault clearance")
        self.adapter.rearm()
        self.state = TipperState.IDLE

    def start(self, front_low: bool, back_low: bool) -> None:
        if self.adapter.estop_latched or self.adapter.communication_fault:
            raise RuntimeError("tipper is disarmed")
        if self.state != TipperState.IDLE or not (front_low and back_low):
            raise RuntimeError("tipper interlock not satisfied")
        self.state = TipperState.LOADING

    def rotate(self, direction: int) -> None:
        if self.adapter.estop_latched or self.adapter.communication_fault:
            raise RuntimeError("tipper is disarmed")
        if self.state != TipperState.LOADING or direction not in (-1, 1):
            raise RuntimeError("tipper not ready to rotate")
        self.direction = direction; self.state = TipperState.ROTATING

    def complete(self) -> None:
        if self.state not in (TipperState.ROTATING, TipperState.RETURNING, TipperState.UNLOADING):
            raise RuntimeError("invalid completion")
        self.state = TipperState.IDLE

    def fail(self, reason: str) -> None:
        self.fault = reason; self.state = TipperState.FAULT
