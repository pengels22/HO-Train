"""Turntable safety primitives and the Pi serial interface to the XIAO controller."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from itertools import count

MAX_APPROACH_MM_S = 25.4


class TurntableSerialController:
    """Bounded JSON command adapter for the dedicated XIAO turntable board."""
    def __init__(self, port, response_timeout_s: float = 0.1):
        self.port = port
        self.response_timeout_s = response_timeout_s
        self._transactions = count(1)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ho-turntable")

    def command(self, name: str, **fields) -> str:
        allowed = {"STATUS", "ESTOP", "STOP", "REARM AUTH", "ENTRY AUTH", "CLEARANCE",
                   "TURN", "POLARITY NORMAL", "POLARITY REVERSED", "POWER ON", "EXIT COMPLETE"}
        if name not in allowed:
            raise ValueError("unsupported turntable command")
        transaction = f"turntable-{next(self._transactions)}"
        payload = {"controller": "turntable", "command": name, "transaction": transaction, **fields}
        future = self._executor.submit(self._exchange, payload)
        try:
            reply = future.result(timeout=self.response_timeout_s)
        except TimeoutError as exc:
            raise TimeoutError(f"turntable {name} acknowledgement timed out") from exc
        if reply.startswith("{"):
            data = json.loads(reply)
            if data.get("transaction") not in (None, transaction):
                raise RuntimeError("turntable transaction mismatch")
            if data.get("error"):
                raise RuntimeError(str(data["error"]))
        return reply

    def _exchange(self, payload: dict) -> str:
        self.port.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("ascii"))
        return self.port.readline().decode("ascii", errors="replace").strip()

    def entry(self, consist_count: int, *, train_stopped: bool, approach_speed_mm_s: float) -> str:
        if consist_count < 1:
            raise ValueError("consist_count must be positive")
        if approach_speed_mm_s > MAX_APPROACH_MM_S:
            raise ValueError("turntable approach exceeds 25.4 mm/s")
        return self.command("ENTRY AUTH", consist_count=consist_count,
                            train_stopped=train_stopped, gap_clear=False)

    def clearance(self, *, train_stopped: bool, gap_clear: bool) -> str:
        return self.command("CLEARANCE", train_stopped=train_stopped, gap_clear=gap_clear)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


@dataclass
class TurntablePulseCounter:
    """Count a configured consist using stable reed CLOSED->OPEN cycles."""
    expected_vehicles: int = 0
    debounce_s: float = 0.015
    cooldown_s: float = 0.500
    count_a: int = 0
    count_b: int = 0
    last_a: float | None = None
    last_b: float | None = None
    cooldown_until_a: float = 0.0
    cooldown_until_b: float = 0.0
    active_a: bool = False
    active_b: bool = False
    fault: str | None = None

    def configure_consist(self, vehicles: int) -> None:
        if vehicles < 1 or vehicles > 32:
            raise ValueError("expected consist must contain 1..32 vehicles")
        self.expected_vehicles = vehicles
        self.reset()

    def pulse(self, end: str, now: float) -> int:
        if end not in {"A", "B"}:
            raise ValueError("turntable end must be A or B")
        last = self.last_a if end == "A" else self.last_b
        cooldown = self.cooldown_until_a if end == "A" else self.cooldown_until_b
        count = self.count_a if end == "A" else self.count_b
        if self.expected_vehicles <= 0:
            raise RuntimeError("expected consist is not configured")
        if count >= self.expected_vehicles and now >= cooldown:
            raise RuntimeError(f"unexpected extra vehicle pulse at turntable end {end}")
        if now < cooldown:
            return count
        if end == "A":
            self.last_a = now; self.count_a += 1
            if self.count_a == self.expected_vehicles: self.cooldown_until_a = now + self.cooldown_s
            return self.count_a
        self.last_b = now; self.count_b += 1
        if self.count_b == self.expected_vehicles: self.cooldown_until_b = now + self.cooldown_s
        return self.count_b

    def reset(self, end: str | None = None) -> None:
        if end not in {None, "A", "B"}:
            raise ValueError("turntable end must be A or B")
        if end in {None, "A"}: self.count_a = 0; self.last_a = None; self.cooldown_until_a = 0
        if end in {None, "B"}: self.count_b = 0; self.last_b = None; self.cooldown_until_b = 0
        if end in {None, "A"}: self.active_a = False
        if end in {None, "B"}: self.active_b = False
        if end is None: self.fault = None

    def signal(self, end: str, active: bool, now: float) -> int:
        """Process a debounced digital level; only inactive->active counts."""
        if end not in {"A", "B"}:
            raise ValueError("turntable end must be A or B")
        was_active = self.active_a if end == "A" else self.active_b
        if end == "A": self.active_a = active
        else: self.active_b = active
        if not active:
            count = self.count_a if end == "A" else self.count_b
            if was_active and count == self.expected_vehicles:
                if end == "A": self.cooldown_until_a = max(self.cooldown_until_a, now + self.cooldown_s)
                else: self.cooldown_until_b = max(self.cooldown_until_b, now + self.cooldown_s)
            return count
        if was_active:
            return self.count_a if end == "A" else self.count_b
        try:
            return self.pulse(end, now)
        except RuntimeError as exc:
            self.fault = str(exc)
            raise

    def complete(self, end: str) -> bool:
        if end not in {"A", "B"}: raise ValueError("turntable end must be A or B")
        return self.expected_vehicles > 0 and (self.count_a if end == "A" else self.count_b) == self.expected_vehicles

    def ready(self, end: str, now: float) -> bool:
        if not self.complete(end):
            return False
        cooldown = self.cooldown_until_a if end == "A" else self.cooldown_until_b
        return now >= cooldown


class TurntableState(str, Enum):
    EMPTY_READY = "EMPTY_READY"
    TRAIN_ENTERING = "TRAIN_ENTERING"
    TRAIN_LOADED = "TRAIN_LOADED"
    ROTATING = "ROTATING"
    ALIGNED_LOADED = "ALIGNED_LOADED"
    TRAIN_EXITING = "TRAIN_EXITING"
    FAULT = "FAULT"


class TurntableController:
    """Simulation/controller state machine with explicit bridge interlocks."""
    def __init__(self, alignment: str = "HOME"):
        if alignment not in {"HOME", "ROTATED"}:
            raise ValueError("turntable must start at HOME or ROTATED")
        self.alignment = alignment
        self.state = TurntableState.EMPTY_READY
        self.target_alignment: str | None = None
        self.motor_on = False
        self.track_power = False
        self.polarity: str | None = None
        self.power_authorized = False
        self.train_stopped = False
        self.clearance_verified = False
        # Physical adapters must update these from independent acknowledgements.
        self.reeds_clear = True
        self.stationary_confirmed = True
        self.gap_clearance_verified = True
        self.communication_ok = True
        self.estop = False
        self.fault: str | None = None
        self.counter = TurntablePulseCounter()

    def _fail(self, reason: str):
        self.motor_on = False; self.track_power = False
        self.state = TurntableState.FAULT; self.fault = reason
        raise RuntimeError(reason)

    def authorize_entry(self, *, track_power: bool, train_stopped: bool, consist_count: int):
        self.counter.configure_consist(consist_count)
        if self.state != TurntableState.EMPTY_READY or not track_power or not train_stopped:
            self._fail("entry authorization interlock")
        self.power_authorized = True; self.train_stopped = True
        self.track_power = True; self.state = TurntableState.TRAIN_ENTERING

    def entry_pulse(self, now: float, active: bool = True) -> int:
        if self.state != TurntableState.TRAIN_ENTERING:
            self._fail("entry pulse outside train entry")
        self.reeds_clear = not active
        return self.counter.signal("A" if self.alignment == "HOME" else "B", active, now)

    def confirm_loaded(self, *, train_stopped: bool, clearance_verified: bool, now: float = float("inf")):
        end = "A" if self.alignment == "HOME" else "B"
        if (not train_stopped or not clearance_verified or not self.reeds_clear or
                not self.stationary_confirmed or not self.gap_clearance_verified or
                not self.counter.ready(end, now)):
            self._fail("loaded train clearance not verified")
        self.train_stopped = True; self.clearance_verified = True
        self.track_power = False; self.state = TurntableState.TRAIN_LOADED

    def begin_rotation(self):
        if self.state != TurntableState.TRAIN_LOADED or self.estop or not self.communication_ok:
            self._fail("rotation interlock")
        if not self.train_stopped or not self.clearance_verified:
            self._fail("train clearance not verified")
        self.target_alignment = "ROTATED" if self.alignment == "HOME" else "HOME"
        self.track_power = False; self.motor_on = True; self.state = TurntableState.ROTATING

    def reach_alignment(self, alignment: str):
        if self.state != TurntableState.ROTATING or alignment != self.target_alignment:
            self._fail("unexpected turntable alignment")
        self.alignment = alignment; self.motor_on = False
        self.state = TurntableState.ALIGNED_LOADED

    def set_polarity(self, polarity: str):
        if polarity not in {"normal", "reversed"}:
            raise ValueError("invalid bridge polarity")
        if self.track_power or self.motor_on:
            self._fail("cannot change polarity while energized")
        self.polarity = polarity

    def authorize_exit(self, *, track_power: bool, train_stopped: bool):
        if self.state != TurntableState.ALIGNED_LOADED or not track_power or not train_stopped:
            self._fail("exit authorization interlock")
        if self.estop or not self.communication_ok or self.polarity is None:
            self._fail("bridge power interlock")
        self.power_authorized = True; self.train_stopped = True
        self.counter.reset()
        self.track_power = True; self.state = TurntableState.TRAIN_EXITING

    def exit_pulse(self, now: float, active: bool = True) -> int:
        if self.state != TurntableState.TRAIN_EXITING:
            self._fail("exit pulse outside train exit")
        end = "B" if self.alignment == "HOME" else "A"
        self.reeds_clear = not active
        return self.counter.signal(end, active, now)

    def confirm_empty(self, *, train_stopped: bool, now: float = float("inf")):
        end = "B" if self.alignment == "HOME" else "A"
        if (not train_stopped or not self.reeds_clear or not self.stationary_confirmed or
                not self.gap_clearance_verified or not self.counter.ready(end, now)):
            self._fail("exit clearance not verified")
        self.track_power = False; self.state = TurntableState.EMPTY_READY
        self.counter.reset(); self.power_authorized = False; self.clearance_verified = False

    def emergency_stop(self, reason: str = "E-Stop"):
        self.estop = True; self.motor_on = False; self.track_power = False
        self.state = TurntableState.FAULT; self.fault = reason

    def communication_lost(self):
        self.communication_ok = False; self._fail("turntable communication fault")

    def rearm(self, *, authorized: bool, alignment: str, faults_clear: bool):
        if not authorized or not faults_clear or alignment not in {"HOME", "ROTATED"}:
            raise RuntimeError("turntable rearm interlock")
        if self.motor_on or self.track_power:
            raise RuntimeError("turntable outputs must be off before rearm")
        self.alignment = alignment; self.estop = False; self.communication_ok = True
        self.fault = None; self.counter.reset(); self.target_alignment = None
        self.state = TurntableState.EMPTY_READY
