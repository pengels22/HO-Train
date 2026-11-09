"""Deterministic, simulation-only locomotive engine.

The engine deliberately refuses to move trains when the surveyed track paths are
not available.  Tests may inject a verified path fixture; production paths are
loaded from the calibration file and must be explicitly marked verified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Callable
import math
import time

from railroad.dispatcher import Dispatcher, SafetyError
from railroad.tracking.receivers import ReceiverEvent


@dataclass(frozen=True)
class SpeedProfile:
    max_speed_mm_s: float = 80.0
    acceleration_mm_s2: float = 40.0
    braking_mm_s2: float = 60.0


@dataclass(frozen=True)
class Car:
    length_mm: float = 120.0
    spacing_mm: float = 25.0
    magnetic_strip: bool = True


@dataclass(frozen=True)
class Consist:
    cars: tuple[Car, ...] = (Car(),)

    @property
    def length_mm(self) -> float:
        return sum(c.length_mm for c in self.cars) + sum(c.spacing_mm for c in self.cars[:-1])


@dataclass
class SimTrain:
    train_id: int
    path_id: str | None = None
    distance_mm: float = 0.0
    speed_mm_s: float = 0.0
    target_speed_mm_s: float = 0.0
    profile: SpeedProfile = field(default_factory=SpeedProfile)
    consist: Consist = field(default_factory=Consist)
    checkpoint_index: int = 0
    hall_index: int = 0
    last_position: tuple[float, float] | None = None


class SimulationEngine:
    """Simulation clock and event producer that drives one Dispatcher."""

    def __init__(self, dispatcher: Dispatcher, paths: dict | None = None,
                 event_sink: Callable[[dict], None] | None = None, clock=None):
        self.dispatcher = dispatcher
        self.paths = paths or {}
        self.event_sink = event_sink
        self.clock = clock or time.monotonic
        self.lock = RLock()
        self.running = False
        self.sim_time = 0.0
        self.multiplier = 1.0
        self.last_wall = self.clock()
        self.faults: set[str] = set()
        self.events: list[dict] = []
        self.trains = {i: SimTrain(i) for i in dispatcher.trains}

    @property
    def geometry_available(self) -> bool:
        return bool(self.paths.get("verified") and self.paths.get("paths"))

    def _log(self, event: str, **data):
        item = {"time": round(self.sim_time, 3), "event": event, **data}
        self.events.append(item)
        self.events[:] = self.events[-500:]
        if self.event_sink:
            self.event_sink(item)

    def start(self):
        with self.lock:
            if not self.geometry_available:
                raise SafetyError("verified surveyed track paths are required before simulation can move")
            self.running = True
            self.last_wall = self.clock()
            self._log("simulation_started", multiplier=self.multiplier)

    def pause(self):
        with self.lock:
            self._integrate_wall()
            self.running = False
            self._log("simulation_paused")

    def resume(self):
        self.start()
        self._log("simulation_resumed", multiplier=self.multiplier)

    def reset(self):
        with self.lock:
            self.running = False
            self.sim_time = 0.0
            self.last_wall = self.clock()
            self.faults.clear()
            self.events.clear()
            for train in self.trains.values():
                train.distance_mm = train.speed_mm_s = train.target_speed_mm_s = 0.0
                train.path_id = None
                train.checkpoint_index = train.hall_index = 0
                train.last_position = None
            self._log("simulation_reset")

    def set_speed(self, multiplier: float):
        if multiplier not in (0.5, 1.0, 2.0, 5.0):
            raise ValueError("speed multiplier must be 0.5, 1, 2, or 5")
        with self.lock:
            self.multiplier = multiplier
            self._log("simulation_speed", multiplier=multiplier)

    def dispatch(self, train_id: int, path_id: str, *, target_speed_mm_s: float | None = None,
                 profile: SpeedProfile | None = None, consist: Consist | None = None):
        with self.lock:
            if not self.geometry_available or path_id not in self.paths["paths"]:
                raise SafetyError("verified surveyed path is not available")
            train = self.trains[train_id]
            train.path_id = path_id
            train.profile = profile or train.profile
            train.consist = consist or train.consist
            train.target_speed_mm_s = target_speed_mm_s if target_speed_mm_s is not None else train.profile.max_speed_mm_s
            train.checkpoint_index = train.hall_index = 0
            self._arm_next_checkpoint(train)
            self._log("route_assigned", train_id=train_id, path_id=path_id)

    def inject_fault(self, fault: str, train_id: int | None = None):
        allowed = {"missed_ir", "stuck_hall", "failed_turnout", "stall", "tipper"}
        if fault not in allowed:
            raise ValueError(f"unknown simulation fault: {fault}")
        with self.lock:
            key = f"{fault}:{train_id}" if train_id is not None else fault
            self.faults.add(key)
            self._log("fault_injected", fault=fault, train_id=train_id)
            if fault == "failed_turnout":
                self.dispatcher.stop_all("turnout confirmation failed")
            elif fault == "tipper":
                self.dispatcher.set_tipper("FAULT", "simulated tipper fault")

    def load(self, train_id: int, location: str):
        with self.lock:
            self.dispatcher.complete_loading(train_id, location)
            self._log("loading_complete", train_id=train_id, location=location, cargo=self.dispatcher.trains[train_id].cargo.value)

    def unload_tipper(self, train_id: int, *, success: bool = True, safe_to_depart: bool = True):
        with self.lock:
            self.dispatcher.set_tipper("PREPARING")
            self._log("tipper_preparing", train_id=train_id)
            self.dispatcher.set_tipper("ROTATING")
            self._log("tipper_rotating", train_id=train_id)
            self.dispatcher.set_tipper("RETURNING")
            self.dispatcher.complete_tipping(train_id, success=success, safe_to_depart=safe_to_depart)
            self.dispatcher.set_tipper("IDLE")
            self._log("tipper_complete" if success else "tipper_failed", train_id=train_id)

    def set_yard_power(self, track: str, enabled: bool):
        with self.lock:
            if track not in ("1", "2", "3"):
                raise ValueError("yard track must be 1, 2, or 3")
            if enabled:
                self.dispatcher.assert_motion_allowed()
            self.dispatcher.yard_power[track] = bool(enabled)
            self._log("yard_power", track=track, enabled=bool(enabled), shared_stalls=("1A", "1B") if track == "1" else ())

    def park(self, train_id: int, stall: str):
        with self.lock:
            track = "1" if stall in ("1A", "1B") else stall
            self.set_yard_power(track, False)
            self.dispatcher.park(train_id, stall)
            self._log("yard_parked", train_id=train_id, stall=stall)

    def acknowledge_and_reconcile(self):
        """Operator acknowledgement; position faults remain latched until inputs reconcile."""
        with self.lock:
            if self.dispatcher.global_stop:
                raise SafetyError("position reconciliation is required before GLOBAL STOP can clear")

    def advance(self, elapsed_s: float):
        with self.lock:
            if elapsed_s < 0:
                raise ValueError("elapsed time cannot be negative")
            if not self.running or self.dispatcher.global_stop:
                return
            dt = elapsed_s * self.multiplier
            self.sim_time += dt
            for train in self.trains.values():
                self._advance_train(train, dt)
            self.dispatcher.check_deadlines(now=self.sim_time)

    def tick(self):
        with self.lock:
            now = self.clock()
            elapsed = max(0.0, now - self.last_wall)
            self.last_wall = now
        self.advance(elapsed)

    def _integrate_wall(self):
        now = self.clock()
        elapsed = max(0.0, now - self.last_wall)
        self.last_wall = now
        if self.running:
            self.advance(elapsed)

    def _path(self, train: SimTrain) -> dict:
        return self.paths["paths"][train.path_id]

    def _arm_next_checkpoint(self, train: SimTrain):
        checkpoints = self._path(train).get("checkpoints", [])
        if train.checkpoint_index < len(checkpoints):
            checkpoint = checkpoints[train.checkpoint_index]
            self.dispatcher.trains[train.train_id].expected_checkpoint = checkpoint["id"]
            self.dispatcher.trains[train.train_id].checkpoint_deadline = self.sim_time + max(2.0, 10.0 / max(train.profile.max_speed_mm_s, 1))

    def _advance_train(self, train: SimTrain, dt: float):
        if not train.path_id:
            return
        fault = f"stall:{train.train_id}" in self.faults or "stall" in self.faults
        target = 0.0 if fault else train.target_speed_mm_s
        rate = train.profile.acceleration_mm_s2 if target > train.speed_mm_s else train.profile.braking_mm_s2
        delta = rate * dt
        train.speed_mm_s = min(target, train.speed_mm_s + delta) if target > train.speed_mm_s else max(target, train.speed_mm_s - delta)
        old = train.distance_mm
        train.distance_mm += train.speed_mm_s * dt
        path = self._path(train)
        length = float(path.get("length_mm", 0))
        train.distance_mm = min(train.distance_mm, length)
        train.last_position = self._interpolate(path.get("points", []), train.distance_mm, length)
        if fault:
            self._log("locomotive_stall", train_id=train.train_id)
            return
        for checkpoint in path.get("checkpoints", []):
            if old < checkpoint["distance_mm"] <= train.distance_mm:
                self._checkpoint(train, checkpoint)
        for hall in path.get("hall_sensors", []):
            if old < hall["distance_mm"] <= train.distance_mm:
                self._hall_event(train, hall)
        for destination in path.get("destinations", []):
            if old < destination["distance_mm"] <= train.distance_mm:
                self._arrival_event(train, destination["destination"])

    def _arrival_event(self, train: SimTrain, destination: str):
        self._log("destination_arrival", train_id=train.train_id, destination=destination)
        try:
            if destination in ("Mine", "Farm"):
                self.load(train.train_id, destination)
            elif destination == "Tipper":
                self.unload_tipper(train.train_id)
            elif destination == "Ski":
                self._log("passenger_stop", train_id=train.train_id, destination="Ski")
        except SafetyError as exc:
            self._log("destination_rejected", train_id=train.train_id, destination=destination, reason=str(exc))

    def _checkpoint(self, train: SimTrain, checkpoint: dict):
        fault = f"missed_ir:{train.train_id}" in self.faults or "missed_ir" in self.faults
        self._log("ir_event", train_id=train.train_id, receiver=checkpoint["id"], missed=fault)
        if fault:
            return
        try:
            event = ReceiverEvent(checkpoint["id"], train.train_id, self.sim_time)
            self.dispatcher.process_ir_event(event, zone=checkpoint.get("zone"))
        except SafetyError:
            return
        train.checkpoint_index += 1
        self._arm_next_checkpoint(train)

    def _hall_event(self, train: SimTrain, hall: dict):
        self._log("hall_event", train_id=train.train_id, sensor=hall["id"], car=hall.get("car_index", 0))
        if f"stuck_hall:{train.train_id}" in self.faults or "stuck_hall" in self.faults:
            return
        if hall.get("last_car", False):
            zone = hall.get("zone") or self.dispatcher.trains[train.train_id].zone
            if zone and self.dispatcher.zones.get(zone) == train.train_id:
                try:
                    self.dispatcher.hall_clear(train.train_id, zone, detected_cars=len(train.consist.cars), expected_cars=len(train.consist.cars))
                    self._log("train_clear", train_id=train.train_id, zone=zone)
                except SafetyError as exc:
                    self._log("hall_clear_rejected", train_id=train.train_id, reason=str(exc))
        train.hall_index += 1

    @staticmethod
    def _interpolate(points: list, distance: float, length: float) -> tuple[float, float] | None:
        if not points:
            return None
        if len(points) == 1 or length <= 0:
            return tuple(points[0][:2])
        target = max(0.0, min(length, distance)) / length * (len(points) - 1)
        i = min(int(target), len(points) - 2)
        fraction = target - i
        a, b = points[i], points[i + 1]
        return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)

    def snapshot(self) -> dict:
        with self.lock:
            self._integrate_wall()
            return {"running": self.running, "sim_time": round(self.sim_time, 3), "multiplier": self.multiplier,
                    "geometry_available": self.geometry_available, "faults": sorted(self.faults),
                    "events": self.events[-100:], "trains": {str(i): {"path_id": t.path_id, "distance_mm": round(t.distance_mm, 2), "speed_mm_s": round(t.speed_mm_s, 2), "position": t.last_position} for i, t in self.trains.items()}}
