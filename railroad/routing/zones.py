"""Configurable operating-zone model and conservative occupancy engine."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

class ZoneState(str, Enum):
    CLEAR = "CLEAR"
    RESERVED = "RESERVED"
    OCCUPIED = "OCCUPIED"
    UNKNOWN = "UNKNOWN"
    FAULT = "FAULT"

@dataclass
class Zone:
    zone_id: str
    railway: str
    color: str
    segments: tuple[str, ...] = ()
    entrances: tuple[str, ...] = ()
    exits: tuple[str, ...] = ()
    neighbors: tuple[str, ...] = ()
    elevation: int | None = None
    hall_sensors: tuple[str, ...] = ()
    ir_checkpoints: tuple[str, ...] = ()
    turnouts: tuple[str, ...] = ()
    state: ZoneState = ZoneState.UNKNOWN
    occupying_train: int | None = None
    reserved_train: int | None = None
    direction: int = 0
    last_event: datetime | None = None
    confidence: float = 0.0
    fault: str | None = None
    verified: bool = False

    def can_enter(self, train_id: int, require_verified: bool = True) -> bool:
        if require_verified and not self.verified:
            return False
        return self.state in (ZoneState.CLEAR, ZoneState.RESERVED) and self.occupying_train in (None, train_id) and self.reserved_train in (None, train_id)

    def reserve(self, train_id: int, require_verified: bool = True) -> None:
        if not self.can_enter(train_id, require_verified):
            raise RuntimeError(f"zone {self.zone_id} is unavailable or unverified")
        self.reserved_train = train_id
        self.state = ZoneState.RESERVED

    def observe_ir(self, train_id: int, checkpoint: str, direction: int = 0) -> None:
        if checkpoint not in self.ir_checkpoints:
            raise ValueError(f"checkpoint {checkpoint} is not assigned to {self.zone_id}")
        self.occupying_train = train_id
        self.direction = direction
        self.confidence = max(self.confidence, 0.6)
        self.last_event = datetime.now(timezone.utc)
        self.state = ZoneState.OCCUPIED

    def observe_hall(self, sensor: str, active: bool) -> None:
        if sensor not in self.hall_sensors:
            raise ValueError(f"sensor {sensor} is not assigned to {self.zone_id}")
        self.last_event = datetime.now(timezone.utc)
        if active and self.state == ZoneState.CLEAR:
            self.state = ZoneState.UNKNOWN
            self.fault = "Hall activation without confirmed locomotive identity"

    def mark_clear(self, train_id: int, consist_cleared: bool) -> None:
        if self.occupying_train not in (None, train_id):
            raise RuntimeError("different train occupies zone")
        if not consist_cleared:
            return
        self.occupying_train = None
        self.confidence = 0.0
        self.state = ZoneState.RESERVED if self.reserved_train else ZoneState.CLEAR
        self.last_event = datetime.now(timezone.utc)

@dataclass
class ZoneEngine:
    zones: dict[str, Zone] = field(default_factory=dict)

    def reserve_route(self, zone_ids: Iterable[str], train_id: int, require_verified: bool = True) -> None:
        requested = list(zone_ids)
        if not requested or any(zone_id not in self.zones for zone_id in requested):
            raise KeyError("route contains unknown zone")
        if not all(self.zones[z].can_enter(train_id, require_verified) for z in requested):
            raise RuntimeError("zone route unavailable")
        for zone_id in requested:
            self.zones[zone_id].reserve(train_id, require_verified)

    def reconcile_ir(self, train_id: int, zone_id: str, checkpoint: str, direction: int = 0) -> None:
        self.zones[zone_id].observe_ir(train_id, checkpoint, direction)

    def conflict(self, zone_ids: Iterable[str], train_id: int) -> bool:
        return any(not self.zones[z].can_enter(train_id, require_verified=False) for z in zone_ids)

    def validate(self) -> list[str]:
        errors: list[str] = []
        ids = set(self.zones)
        for zone in self.zones.values():
            if len(zone.zone_id.split("-")) != 2:
                errors.append(f"invalid zone id: {zone.zone_id}")
            errors.extend(f"{zone.zone_id}: unknown neighbor {n}" for n in zone.neighbors if n not in ids)
            errors.extend(f"{zone.zone_id}: unknown segment {s}" for s in zone.segments if not s)
        return errors
