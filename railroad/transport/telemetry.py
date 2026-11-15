"""Strict, versioned locomotive telemetry and controller health monitoring."""
from __future__ import annotations
from dataclasses import dataclass
import json
from threading import Event, RLock, Thread
import time

MAGIC = b"HT"
VERSION = 1
STATES = frozenset({"DISARMED", "ARMED", "ESTOP_LATCHED", "COMMUNICATION_FAULT"})
MAX_U32 = 0xFFFFFFFF

@dataclass(frozen=True)
class LocomotiveTelemetry:
    locomotive_id: int
    state: str
    estop: bool
    communication_fault: bool
    armed: bool
    speed: int
    sequence: int
    session: str
    uptime_ms: int
    last_command_sequence: int = 0
    rearm_transaction: str | None = None

    def encode(self) -> bytes:
        body = {"version": VERSION, "id": self.locomotive_id, "state": self.state,
                "estop": self.estop, "communication_fault": self.communication_fault,
                "armed": self.armed, "speed": self.speed, "sequence": self.sequence,
                "last_command_sequence": self.last_command_sequence,
                "session": self.session, "uptime_ms": self.uptime_ms}
        if self.rearm_transaction is not None:
            body["rearm_transaction"] = self.rearm_transaction
        return MAGIC + json.dumps(body, separators=(",", ":"), sort_keys=True).encode()

    @classmethod
    def decode(cls, packet: bytes) -> "LocomotiveTelemetry":
        if not isinstance(packet, (bytes, bytearray)) or not packet.startswith(MAGIC):
            raise ValueError("invalid telemetry magic")
        try:
            body = json.loads(bytes(packet[2:]).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid telemetry JSON") from exc
        if not isinstance(body, dict) or body.get("version") != VERSION:
            raise ValueError("invalid telemetry fields or version")
        required = {"id", "state", "estop", "communication_fault", "armed", "speed", "sequence", "session", "uptime_ms"}
        if not required <= body.keys():
            raise ValueError("missing telemetry field")
        if type(body["id"]) is not int or not 1 <= body["id"] <= 4:
            raise ValueError("invalid locomotive telemetry ID")
        if type(body["state"]) is not str or body["state"] not in STATES:
            raise ValueError("invalid locomotive state")
        for key in ("estop", "communication_fault", "armed"):
            if type(body[key]) is not bool:
                raise ValueError(f"invalid telemetry boolean: {key}")
        for key in ("sequence", "uptime_ms"):
            if type(body[key]) is not int or not 0 <= body[key] <= MAX_U32:
                raise ValueError(f"invalid telemetry integer: {key}")
        last_command = body.get("last_command_sequence", 0)
        if type(last_command) is not int or not 0 <= last_command <= MAX_U32:
            raise ValueError("invalid last command sequence")
        if type(body["speed"]) is not int or not -255 <= body["speed"] <= 255:
            raise ValueError("invalid locomotive speed")
        if type(body["session"]) is not str or not 1 <= len(body["session"]) <= 64:
            raise ValueError("invalid boot session")
        transaction = body.get("rearm_transaction")
        if transaction is not None and (type(transaction) is not str or not 1 <= len(transaction) <= 128):
            raise ValueError("invalid rearm transaction")
        return cls(body["id"], body["state"], body["estop"], body["communication_fault"], body["armed"], body["speed"], body["sequence"], body["session"], body["uptime_ms"], last_command, transaction)

class ControllerHealthRegistry:
    """Thread-safe health view; sequences are monotonic within each boot session."""
    def __init__(self, usb_registry, locomotive_ids=(), freshness_s: float = 0.75,
                 clock=time.monotonic, *, independent_locomotives: bool = False):
        self.usb_registry = usb_registry
        self.required_locomotives = set(locomotive_ids)
        self.independent_locomotives = bool(independent_locomotives)
        self.freshness_s = float(freshness_s)
        self.clock = clock
        self.telemetry = {}
        self._sessions, self._sequences, self._retired_sessions, self._failures, self._rearm = {}, {}, {}, set(), {}
        self._rearm_event, self._lock = Event(), RLock()
        self._monitor_thread = self._monitor_stop = None
        self.on_failure = None
        usb_registry.on_failure = self._usb_failure

    def _fail(self, controller, reason):
        key = f"{controller}:{reason}"
        if key not in self._failures:
            self._failures.add(key)
            if self.on_failure: self.on_failure(controller, reason)

    def _clear_failure(self, controller, *, preserve_restart=True):
        self._failures = {key for key in self._failures if not (key.startswith(f"{controller}:") and (not preserve_restart or "restart" not in key))}

    def _usb_failure(self, controller, reason): self._fail(str(controller), reason)

    def update(self, packet: bytes, now: float | None = None):
        telemetry = LocomotiveTelemetry.decode(packet)
        if telemetry.locomotive_id not in self.required_locomotives:
            raise ValueError("telemetry is not from a configured locomotive")
        received = self.clock() if now is None else now
        with self._lock:
            ident, old = telemetry.locomotive_id, self._sessions.get(telemetry.locomotive_id)
            retired = self._retired_sessions.setdefault(ident, set())
            if telemetry.session in retired:
                raise ValueError("telemetry from retired controller session")
            if old is not None and telemetry.session != old:
                retired.add(old)
                self._sessions[ident], self._sequences[ident] = telemetry.session, -1
                self._rearm.pop(ident, None)
                self._fail(f"locomotive-{ident}", "controller restart; rearm required")
            elif old is not None and telemetry.sequence <= self._sequences[ident]:
                raise ValueError("duplicate or out-of-order telemetry")
            else:
                self._sessions[ident] = telemetry.session
            self._sequences[ident] = telemetry.sequence
            self.telemetry[ident] = (telemetry, received)
            pending = self._rearm.get(ident)
            if pending and received >= pending["requested_at"]:
                if pending["session"] is None:
                    pending["session"] = telemetry.session
                if (telemetry.session == pending["session"] and telemetry.rearm_transaction == pending["transaction"] and
                        telemetry.armed and not telemetry.estop and not telemetry.communication_fault and telemetry.speed == 0):
                    pending["ack"] = True; self._rearm_event.set()
            if telemetry.communication_fault or telemetry.estop:
                self._fail(f"locomotive-{ident}", "reported unsafe state")
        return telemetry

    def begin_rearm(self, transaction):
        with self._lock:
            self._rearm_event.clear()
            ids = self.telemetry.keys() if self.independent_locomotives else self.required_locomotives
            self._rearm = {i: {"transaction": transaction, "session": self._sessions.get(i), "requested_at": self.clock(), "ack": False} for i in ids}

    def wait_for_rearm(self, transaction, timeout=0.75):
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            with self._lock:
                if any(item["transaction"] != transaction for item in self._rearm.values()):
                    return False
                if all(x["ack"] for x in self._rearm.values()): return True
            self._rearm_event.wait(max(0.0, min(0.05, deadline - self.clock())))
        return False

    def check_freshness(self, now=None):
        now = self.clock() if now is None else now
        for ident in self.required_locomotives:
            item = self.telemetry.get(ident)
            if item is None and self.independent_locomotives:
                continue
            if item is None or now - item[1] > self.freshness_s:
                self._fail(f"locomotive-{ident}", "telemetry stale or missing")

    def start_monitor(self, period_s=0.1):
        if self._monitor_thread is not None: return
        self._monitor_stop = Event()
        def loop():
            while not self._monitor_stop.wait(period_s):
                try:
                    self.check_freshness(); self.usb_registry.all_required_ready()
                except Exception as exc: self._fail("controller-health", str(exc))
        self._monitor_thread = Thread(target=loop, name="ho-controller-health", daemon=True)
        self._monitor_thread.start()

    def stop_monitor(self):
        if self._monitor_stop is not None: self._monitor_stop.set()
        if self._monitor_thread is not None: self._monitor_thread.join(timeout=1.0)
        self._monitor_thread = self._monitor_stop = None

    def rearm_ready(self):
        now = self.clock(); self.check_freshness(now)
        with self._lock:
            ids = set(self.telemetry) if self.independent_locomotives else self.required_locomotives
            fresh = all(now - self.telemetry[i][1] <= self.freshness_s for i in ids)
            ready = all(t.armed and not t.estop and not t.communication_fault and t.speed == 0 for i, (t, _) in self.telemetry.items() if i in ids)
            no_loco_faults = all(not any(key.startswith(f"locomotive-{i}:") for key in self._failures) for i in ids)
            acknowledgements = not self._rearm or all(item["ack"] for item in self._rearm.values())
            return self.usb_registry.all_required_ready() and acknowledgements and (not ids or (fresh and ready and no_loco_faults))

    def operating_ready(self, locomotive_id: int | None = None):
        """Health gate for motion; unlike rearm, a moving train may be nonzero speed."""
        now = self.clock(); self.check_freshness(now)
        with self._lock:
            if locomotive_id is None and self.independent_locomotives:
                return self.usb_registry.all_required_ready()
            if locomotive_id is not None:
                item = self.telemetry.get(int(locomotive_id))
                if item is None or now - item[1] > self.freshness_s:
                    return False
                telemetry, _ = item
                return (self.usb_registry.all_required_ready() and telemetry.state == "ARMED" and
                        telemetry.armed and not telemetry.estop and not telemetry.communication_fault and
                        not any(k.startswith(f"locomotive-{int(locomotive_id)}:") for k in self._failures))
            fresh = all(i in self.telemetry and now - self.telemetry[i][1] <= self.freshness_s for i in self.required_locomotives)
            safe = all(t.state == "ARMED" and t.armed and not t.estop and not t.communication_fault
                       for t, _ in self.telemetry.values() if t.locomotive_id in self.required_locomotives)
            no_faults = all(not any(k.startswith(f"locomotive-{i}:") for k in self._failures) for i in self.required_locomotives)
            return self.usb_registry.all_required_ready() and (not self.required_locomotives or (fresh and len(self.telemetry) == len(self.required_locomotives) and safe and no_faults))

    # Compatibility name for callers that used the old, rearm-only method.
    def all_required_ready(self):
        return self.rearm_ready()

    def reconcile(self, controller_id) -> None:
        """Explicitly clear a controller fault after current safe status is verified."""
        with self._lock:
            if isinstance(controller_id, int):
                if controller_id not in self.required_locomotives:
                    raise ValueError("controller is not required/configured")
                item = self.telemetry.get(controller_id)
                if item is None:
                    raise ValueError("controller telemetry is missing")
                telemetry, received = item
                if self.clock() - received > self.freshness_s or telemetry.state != "ARMED" or telemetry.estop or telemetry.communication_fault:
                    raise ValueError("controller is not in a fresh safe state")
                self._clear_failure(f"locomotive-{controller_id}", preserve_restart=False)
                return
            controller = next((item for item in self.usb_registry.controllers if item.controller_id == controller_id), None)
            if controller is None or not controller.connected or controller.last_error or controller.faults:
                raise ValueError("USB controller is not in a fresh safe state")
            self._clear_failure(str(controller_id), preserve_restart=False)

    def failures(self):
        with self._lock:
            return tuple(sorted(self._failures))

    def status(self):
        result = list(self.usb_registry.status()); now = self.clock()
        with self._lock:
            for ident in sorted(self.required_locomotives):
                item = self.telemetry.get(ident)
                if item is None:
                    result.append({"id": f"locomotive-{ident}", "type": "m5_atom_echo", "required": not self.independent_locomotives, "connected": False, "state": None, "faults": ["telemetry_missing"], "unverified": True}); continue
                telemetry, received = item
                faults = [key.split(":", 1)[1] for key in self._failures if key.startswith(f"locomotive-{ident}:")]
                if telemetry.communication_fault and "reported unsafe state" not in faults:
                    faults.append("reported unsafe state")
                result.append({"id": f"locomotive-{ident}", "type": "m5_atom_echo", "required": not self.independent_locomotives, "connected": now - received <= self.freshness_s, "state": telemetry.state, "faults": faults, "armed": telemetry.armed, "estop": telemetry.estop, "last_sequence": telemetry.sequence, "last_command_sequence": telemetry.last_command_sequence, "session": telemetry.session, "last_success": received})
        return result
