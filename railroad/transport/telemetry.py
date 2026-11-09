"""Versioned locomotive telemetry packets; separate from the 12-byte command frame."""
from __future__ import annotations
from dataclasses import dataclass
import json
import time

MAGIC = b"HT"
VERSION = 1

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

    def encode(self) -> bytes:
        body = {"version": VERSION, "id": self.locomotive_id, "state": self.state,
                "estop": self.estop, "communication_fault": self.communication_fault,
                "armed": self.armed, "speed": self.speed, "sequence": self.sequence,
                "session": self.session, "uptime_ms": self.uptime_ms}
        return MAGIC + json.dumps(body, separators=(",", ":"), sort_keys=True).encode()

    @classmethod
    def decode(cls, packet: bytes) -> "LocomotiveTelemetry":
        if not packet.startswith(MAGIC):
            raise ValueError("invalid telemetry magic")
        try: body = json.loads(packet[2:].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise ValueError("invalid telemetry JSON") from exc
        required = {"version", "id", "state", "estop", "communication_fault", "armed", "speed", "sequence", "session", "uptime_ms"}
        if body.keys() < required or body["version"] != VERSION:
            raise ValueError("invalid telemetry fields or version")
        if not isinstance(body["id"], int) or not 1 <= body["id"] <= 4:
            raise ValueError("invalid locomotive telemetry ID")
        return cls(body["id"], str(body["state"]), bool(body["estop"]), bool(body["communication_fault"]), bool(body["armed"]), int(body["speed"]), int(body["sequence"]), str(body["session"]), int(body["uptime_ms"]))


class ControllerHealthRegistry:
    """Single logical health view over registered USB and locomotive telemetry."""
    def __init__(self, usb_registry, locomotive_ids=(), freshness_s: float = 0.75):
        self.usb_registry = usb_registry
        self.required_locomotives = set(locomotive_ids)
        self.freshness_s = freshness_s
        self.telemetry: dict[int, tuple[LocomotiveTelemetry, float]] = {}
        self.on_failure = None
        usb_registry.on_failure = self._usb_failure

    def _usb_failure(self, controller, reason):
        if self.on_failure: self.on_failure(controller, reason)

    def update(self, packet: bytes, now: float | None = None) -> LocomotiveTelemetry:
        telemetry = LocomotiveTelemetry.decode(packet)
        if telemetry.locomotive_id not in self.required_locomotives:
            raise ValueError("telemetry is not from a configured locomotive")
        self.telemetry[telemetry.locomotive_id] = (telemetry, time.monotonic() if now is None else now)
        if telemetry.communication_fault or telemetry.estop:
            if self.on_failure: self.on_failure(f"locomotive-{telemetry.locomotive_id}", "reported unsafe state")
        return telemetry

    def check_freshness(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for locomotive_id in self.required_locomotives:
            item = self.telemetry.get(locomotive_id)
            if item is None or now - item[1] > self.freshness_s:
                if self.on_failure: self.on_failure(f"locomotive-{locomotive_id}", "telemetry stale or missing")

    def all_required_ready(self) -> bool:
        now = time.monotonic()
        fresh = True
        for locomotive_id in self.required_locomotives:
            item = self.telemetry.get(locomotive_id)
            if item is None or now - item[1] > self.freshness_s:
                fresh = False
        self.check_freshness(now)
        usb_ready = self.usb_registry.all_required_ready()
        loco_ready = all(t.armed and not t.estop and not t.communication_fault
                         for t, _ in self.telemetry.values()
                         if t.locomotive_id in self.required_locomotives)
        return usb_ready and fresh and len(self.telemetry) == len(self.required_locomotives) and loco_ready

    def status(self) -> list[dict]:
        result = list(self.usb_registry.status())
        now = time.monotonic()
        for locomotive_id in sorted(self.required_locomotives):
            item = self.telemetry.get(locomotive_id)
            if item is None:
                result.append({"id": f"locomotive-{locomotive_id}", "type": "m5_atom_echo", "required": True, "connected": False, "state": None, "faults": ["telemetry_missing"], "unverified": True})
                continue
            telemetry, received = item
            result.append({"id": f"locomotive-{locomotive_id}", "type": "m5_atom_echo", "required": True, "connected": now - received <= self.freshness_s, "state": telemetry.state, "faults": ["communication_fault"] if telemetry.communication_fault else [], "armed": telemetry.armed, "estop": telemetry.estop, "last_sequence": telemetry.sequence, "session": telemetry.session, "last_success": received})
        return result
