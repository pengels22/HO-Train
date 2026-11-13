"""Dispatcher and interlocks shared by simulation and Raspberry Pi hardware."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
import time
from typing import Callable

ZONES = tuple(f"{line}-{n}" for line in ("SKI", "FARM", "UND", "MINE", "MAIN") for n in (1, 2, 3))
STALLS = ("1A", "1B", "2", "3")
TURNOUT_DEFAULTS = {"A":"diverging", "B":"straight", "C":"straight", "D":"straight", "E":"straight", "F":"straight", "G":"straight", "H":"straight"}
TIPPER_LOCKED = frozenset(("MAIN-3", "UND-1"))
DESTINATIONS = ("Mine", "Farm", "Ski", "Town", "Tipper", "Turntable", "Yard")
SLOW_DESTINATIONS = frozenset(("Tipper", "Turntable"))
MAX_SLOW_DESTINATION_MM_S = 25.4

class SafetyError(RuntimeError):
    pass

class Cargo(str, Enum):
    EMPTY="EMPTY"
    CORN="CORN"
    ORE="ORE"
    UNKNOWN="UNKNOWN"

@dataclass
class Train:
    train_id: int
    name: str
    kind: str = "freight"
    zone: str | None = None
    destination: str | None = None
    cargo: Cargo = Cargo.EMPTY
    velocity: int = 0
    parked: str | None = None
    last_checkpoint: str | None = None
    estimate_mm: float = 0.0
    last_observed: float | None = None
    expected_checkpoint: str | None = None
    checkpoint_deadline: float | None = None
    cycle: list[str] = field(default_factory=list)
    cycle_step: int = 0

@dataclass
class Dispatcher:
    trains: dict[int, Train] = field(default_factory=lambda: {
        n: Train(n, f"Train {n}", kind="passenger" if n==4 else "freight")
        for n in range(1,5)
    })
    zones: dict[str, int | None] = field(default_factory=lambda: {z:None for z in ZONES})
    reservations: dict[str, int | None] = field(default_factory=lambda: {z:None for z in ZONES})
    destinations: dict[str, int | None] = field(default_factory=dict)
    turnouts: dict[str,str] = field(default_factory=lambda: TURNOUT_DEFAULTS.copy())
    yard_power: dict[str,bool] = field(default_factory=lambda: {"1":False,"2":False,"3":False})
    tipper: str = "IDLE"
    tipper_fault: str | None = None
    global_stop: bool = False
    stop_reason: str | None = None
    stop_causes: dict[str, str] = field(default_factory=dict)
    simulation: bool = True
    estop_controller: object | None = field(default=None, repr=False)
    physical_estop: Callable[[], bool] | None = field(default=None, repr=False)
    accessory_stops: dict[str, Callable[[], None]] = field(default_factory=dict, repr=False)
    motion_stops: list[Callable[[], None]] = field(default_factory=list, repr=False)
    accessory_errors: dict[str, str] = field(default_factory=dict, repr=False)
    controller_health: object | None = field(default=None, repr=False)
    # Calibrated physical velocity at full command, per locomotive. None means
    # the locomotive is not authorized for automatic slow-destination motion.
    speed_mm_s_at_255: dict[int, float | None] = field(default_factory=dict, repr=False)
    _rearm_required: bool = field(default=False, repr=False)
    lock: RLock = field(default_factory=RLock, repr=False)

    def attach_estop(self, controller, *, require_rearm: bool = True) -> None:
        """Attach the sole hardware command gate.

        Simulation uses the dispatcher latch without a network sender. Hardware
        and bench runtimes attach ``EmergencyStop`` explicitly at startup.
        """
        with self.lock:
            self.estop_controller = controller
            self._rearm_required = require_rearm

    def disarm(self) -> None:
        """Put the runtime behind the explicit rearm gate."""
        with self.lock:
            self._rearm_required = True

    def attach_physical_estop(self, is_pressed: Callable[[], bool]) -> None:
        with self.lock:
            self.physical_estop = is_pressed

    def attach_accessory_stops(self, **stops: Callable[[], None]) -> None:
        """Register allow-listed tipper/turntable/accessory stop callbacks."""
        with self.lock:
            self.accessory_stops.update({k: v for k, v in stops.items() if v is not None})

    def attach_controller_health(self, registry) -> None:
        with self.lock:
            self.controller_health = registry
            def on_failure(controller, reason):
                if str(controller).startswith("locomotive-"):
                    try:
                        train_id = int(str(controller).split("-", 1)[1])
                        self.trains[train_id].velocity = 0
                    except (ValueError, KeyError):
                        pass
                    return
                self.stop_all(f"controller {controller} communication failure: {reason}", cause="controller_fault")
            registry.on_failure = on_failure

    def attach_motion_stop(self, callback: Callable[[], None]) -> None:
        """Register a local motion engine stop hook.

        This is deliberately separate from accessory callbacks: a global stop
        must invalidate simulated targets before any later clock tick.
        """
        with self.lock:
            if callback not in self.motion_stops:
                self.motion_stops.append(callback)

    @property
    def estop_active(self) -> bool:
        return bool(self.estop_controller and self.estop_controller.active)

    @property
    def tipper_locked(self) -> bool:
        return self.tipper != "IDLE" or self.tipper_fault is not None

    def _cause_for_reason(self, reason: str) -> str:
        text = reason.lower()
        if "physical" in text: return "physical_estop"
        if "tipper" in text: return "tipper_fault"
        if "turntable" in text: return "turntable_fault"
        if "checkpoint" in text or "missed" in text or "unexpected" in text: return "checkpoint_fault"
        if "controller" in text or "communication" in text: return "controller_fault"
        if "operator" in text: return "operator_estop"
        return "safety_fault"

    def stop_all(self, reason: str, *, cause: str | None = None):
        with self.lock:
            self.global_stop = True
            self.stop_reason = self.stop_reason or reason
            self.stop_causes[cause or self._cause_for_reason(reason)] = reason
            self._rearm_required = True
            for t in self.trains.values():
                t.velocity = 0
            for stop in tuple(self.motion_stops):
                try:
                    stop()
                except Exception as exc:
                    self.accessory_errors["motion_engine"] = str(exc)
            if self.estop_controller:
                try:
                    self.estop_controller.activate()
                except Exception as exc:
                    self.accessory_errors["estop_transport"] = str(exc)
            for name, stop in self.accessory_stops.items():
                try:
                    stop()
                    self.accessory_errors.pop(name, None)
                except Exception as exc:
                    # Continue to UDP/other controllers even if one accessory
                    # controller is disconnected.
                    self.accessory_errors[name] = str(exc)

    def release_estop(self) -> None:
        """Release only the physical cause; all other causes remain latched."""
        with self.lock:
            self.stop_causes.pop("physical_estop", None)
            if self.estop_controller and not self.stop_causes:
                self.estop_controller.clear()

    def clear_stop(self):
        with self.lock:
            if self.tipper_fault:
                raise SafetyError("tipper fault must be resolved first")
            if self.physical_estop and self.physical_estop():
                raise SafetyError("physical E-Stop remains engaged")
            if self.accessory_errors:
                raise SafetyError("E-Stop accessory faults remain unresolved")
            if any(t.expected_checkpoint and t.checkpoint_deadline and
                   time.monotonic() > t.checkpoint_deadline for t in self.trains.values()):
                raise SafetyError("unresolved checkpoint position fault")
            if "checkpoint_fault" in self.stop_causes:
                unresolved = any(t.expected_checkpoint for t in self.trains.values())
                if unresolved:
                    raise SafetyError("unresolved checkpoint position fault")
                self.stop_causes.pop("checkpoint_fault", None)
            for cause in ("operator_estop", "safety_fault"):
                self.stop_causes.pop(cause, None)
            if self.stop_causes:
                raise SafetyError("active stop causes remain: " + ", ".join(sorted(self.stop_causes)))
            self.global_stop = False
            self.stop_reason = None
            # Clearing the broadcast is not permission to move.  The explicit
            # rearm step below is intentionally separate.
            if self.estop_controller:
                self.estop_controller.clear()

    def rearm(self):
        """Explicitly rearm after an operator has reconciled the layout."""
        with self.lock:
            if self.global_stop:
                raise SafetyError("clear GLOBAL STOP before rearming")
            if self.physical_estop and self.physical_estop():
                raise SafetyError("physical E-Stop remains engaged")
            if self.tipper_fault or self.accessory_errors:
                raise SafetyError("safety faults remain unresolved")
            transaction = f"rearm-{time.monotonic_ns()}"
            if self.controller_health:
                self.controller_health.begin_rearm(transaction)
            if self.estop_controller:
                try:
                    self.estop_controller.rearm(transaction)
                except TypeError:
                    self.estop_controller.rearm()
            if self.controller_health and self.controller_health.required_locomotives:
                if not self.controller_health.wait_for_rearm(transaction):
                    raise SafetyError("required locomotive rearm acknowledgements are not ready")
            if self.controller_health and not self.controller_health.rearm_ready():
                raise SafetyError("required controller acknowledgements are not ready")
            self._rearm_required = False

    def command_motion(self, train_id: int, speed: int) -> None:
        """Set a commanded speed through the E-Stop gate.

        This is the dispatcher-facing path for hardware command writers; it
        cannot issue a nonzero command while stopped, latched, or disarmed.
        """
        with self.lock:
            self.assert_motion_allowed(train_id)
            if train_id not in self.trains:
                raise KeyError(train_id)
            self._enforce_destination_speed(train_id, speed)
            if self.estop_controller:
                self.estop_controller.send_motion(train_id, speed)
            self.trains[train_id].velocity = int(speed)

    def set_speed_calibration(self, train_id: int, mm_s_at_255: float | None) -> None:
        """Set measured full-command speed; null deliberately disables unknown hardware."""
        if mm_s_at_255 is not None and mm_s_at_255 <= 0:
            raise ValueError("calibrated speed must be positive")
        self.speed_mm_s_at_255[train_id] = mm_s_at_255

    def _enforce_destination_speed(self, train_id: int, speed: int) -> None:
        destination = self.trains[train_id].destination
        if destination not in SLOW_DESTINATIONS or speed == 0:
            return
        calibrated = self.speed_mm_s_at_255.get(train_id)
        if calibrated is None:
            raise SafetyError(f"train {train_id} has no calibrated speed for {destination}")
        measured = abs(speed) / 255 * calibrated
        if measured > MAX_SLOW_DESTINATION_MM_S + 1e-9:
            raise SafetyError(f"{destination} approach exceeds {MAX_SLOW_DESTINATION_MM_S} mm/s")

    def assert_motion_allowed(self, train_id: int | None = None) -> None:
        if self.global_stop or self._rearm_required:
            raise SafetyError("motion command blocked by E-Stop/disarmed state")
        if self.physical_estop and self.physical_estop():
            raise SafetyError("physical E-Stop remains engaged")
        if self.tipper_fault or self.accessory_errors:
            raise SafetyError("safety faults remain unresolved")
            if self.controller_health and not self.controller_health.operating_ready(train_id):
                raise SafetyError(f"locomotive {train_id} controller health is not ready")

    def reconcile_controller(self, locomotive_id) -> None:
        """Operator-authorized reconciliation; never called by telemetry arrival."""
        with self.lock:
            if not self.controller_health:
                raise SafetyError("controller health is not configured")
            controller_id = int(locomotive_id) if isinstance(locomotive_id, int) or str(locomotive_id).isdigit() else str(locomotive_id)
            self.controller_health.reconcile(controller_id)
            if not self.controller_health.failures():
                self.stop_causes.pop("controller_fault", None)

    def set_tipper(self, state: str, reason: str | None = None):
        with self.lock:
            if state not in {"IDLE","PREPARING","ROTATING","RETURNING","FAULT"}:
                raise ValueError("invalid tipper state")
            if state in {"PREPARING", "ROTATING", "RETURNING"}:
                self.assert_motion_allowed()
            if self.tipper_fault and state != "FAULT":
                raise SafetyError("clear the fault explicitly before returning to idle")
            self.tipper = state
            if state == "FAULT":
                self.tipper_fault = reason or "tipper failed"
                for t in self.trains.values():
                    if t.destination == "Tipper":
                        t.cargo = Cargo.UNKNOWN
                        t.destination = "Yard"
                        t.cycle = []
                        t.cycle_step = 0
                        t.velocity = 0
                self.stop_all("tipper fault: check mechanical safety before recovery")

    def clear_tipper_fault(self, home: bool, restraints_released: bool, track_clear: bool):
        with self.lock:
            if not (home and restraints_released and track_clear):
                raise SafetyError("home, restraints, and track-clear confirmations required")
            self.tipper_fault = None
            self.tipper = "IDLE"
            self.stop_causes.pop("tipper_fault", None)
            # Does not independently reset global stop or restore prior routes.

    def route_available(self, train_id: int, zones: list[str], *, mine_transit=False) -> bool:
        if self.global_stop or self._rearm_required or train_id not in self.trains:
            return False
        if self.physical_estop and self.physical_estop():
            return False
        if self.tipper_fault or self.accessory_errors:
            return False
        if len(zones) != len(set(zones)) or any(z not in self.zones for z in zones):
            return False
        for zone in zones:
            if self.tipper_locked and zone in TIPPER_LOCKED:
                # MAIN-2 -> Mine uses A straight without entering the MAIN-3 protected segment.
                # The dispatcher must not represent this exception as free access to MAIN-3.
                return False
            if self.zones[zone] not in (None, train_id) or self.reservations[zone] not in (None, train_id):
                return False
        return True

    def reserve(self, train_id: int, zones: list[str], destination: str | None = None):
        with self.lock:
            if not self.route_available(train_id, zones):
                raise SafetyError("zone unavailable or protected")
            if destination and self.destinations.get(destination) not in (None,train_id):
                raise SafetyError("destination occupied/reserved")
            for z in zones:
                self.reservations[z] = train_id
            if destination:
                self.destinations[destination] = train_id
                self.trains[train_id].destination = destination

    def enter(self, train_id: int, zone: str):
        with self.lock:
            if self.global_stop or self._rearm_required or zone not in self.zones or (self.tipper_locked and zone in TIPPER_LOCKED):
                raise SafetyError("unsafe zone entry")
            if self.zones[zone] not in (None,train_id) or self.reservations[zone] != train_id:
                raise SafetyError("zone not exclusively reserved")
            self.zones[zone] = train_id
            self.trains[train_id].zone = zone

    def tail_clear(self, train_id: int, zone: str, *, last_car_confirmed: bool):
        with self.lock:
            if not last_car_confirmed or self.zones.get(zone) != train_id:
                raise SafetyError("last car not confirmed clear")
            self.zones[zone] = None
            self.reservations[zone] = None

    def assign_destination(self, train_id: int, destination: str):
        with self.lock:
            if self.global_stop or self._rearm_required: raise SafetyError("global stop/disarmed")
            if destination not in DESTINATIONS: raise ValueError("unknown destination")
            train = self.trains[train_id]
            if train.kind=="passenger" and destination in ("Mine","Farm","Tipper"):
                raise SafetyError("passenger train cannot perform freight operations")
            if train.kind=="freight" and destination in ("Mine","Farm"):
                if train.cargo != Cargo.EMPTY:
                    raise SafetyError("freight must complete tipper unloading before new load")
            if destination=="Tipper" and train.cargo not in (Cargo.CORN,Cargo.ORE):
                raise SafetyError("only loaded freight can be tipped")
            if self.destinations.get(destination) not in (None,train_id):
                raise SafetyError("destination in use")
            if train.destination and self.destinations.get(train.destination)==train_id:
                del self.destinations[train.destination]
            self.destinations[destination]=train_id
            train.destination=destination

    def complete_loading(self, train_id: int, location: str):
        with self.lock:
            self.assert_motion_allowed()
            train=self.trains[train_id]
            if train.kind!="freight" or train.cargo != Cargo.EMPTY or train.destination != location:
                raise SafetyError("unexpected loading operation")
            if location not in ("Mine","Farm"): raise ValueError("invalid freight loading point")
            train.cargo = Cargo.ORE if location=="Mine" else Cargo.CORN

    def complete_tipping(self, train_id: int, *, success: bool, safe_to_depart: bool):
        with self.lock:
            train=self.trains[train_id]
            if not success:
                train.cargo=Cargo.UNKNOWN
                train.destination="Yard"
                train.cycle=[]
                train.velocity=0
                if not safe_to_depart:
                    self.stop_all("tipper failed and train unsafe to depart")
                return
            if train.cargo not in (Cargo.ORE,Cargo.CORN):
                raise SafetyError("no confirmed cargo to unload")
            train.cargo=Cargo.EMPTY

    def set_cycle(self, train_id:int, steps:list[str]):
        with self.lock:
            train=self.trains[train_id]
            if not steps or any(s not in DESTINATIONS for s in steps):
                raise ValueError("cycle has invalid steps")
            if train.kind=="passenger" and any(s in ("Mine","Farm","Tipper") for s in steps):
                raise SafetyError("passenger cycle cannot handle freight")
            # Every repeated farm/mine pickup must have an intervening tipper.
            last_source=None
            tipped=True
            for step in steps + steps:
                if step in ("Mine","Farm"):
                    if not tipped:
                        raise SafetyError("freight must visit tipper before another pickup")
                    last_source=step
                    tipped=False
                elif step=="Tipper":
                    if not last_source:
                        raise SafetyError("tipper step without prior material pickup")
                    tipped=True
            train.cycle=list(steps);train.cycle_step=0

    def hall_clear(self, train_id: int, zone: str, *, detected_cars: int, expected_cars: int):
        if expected_cars<=0 or detected_cars<expected_cars:
            raise SafetyError("sensor clear occurred between cars; rear not verified")
        self.tail_clear(train_id,zone,last_car_confirmed=True)

    def checkpoint(self, train_id:int, receiver:str, zone:str|None=None, now:float|None=None):
        with self.lock:
            if train_id not in self.trains: raise KeyError(train_id)
            train=self.trains[train_id]
            if train.expected_checkpoint and receiver!=train.expected_checkpoint:
                self.stop_all(f"unexpected checkpoint {receiver} for train {train_id}")
                raise SafetyError("checkpoint sequence mismatch")
            train.last_checkpoint=receiver
            train.last_observed=time.monotonic() if now is None else now
            train.expected_checkpoint=None
            train.checkpoint_deadline=None
            if zone is not None: train.zone=zone

    def process_ir_event(self, event, zone: str | None = None):
        """Common entry point for decoded Nano events and simulated IR events."""
        return self.checkpoint(event.train_id, event.receiver_id, zone=zone, now=event.timestamp)

    def check_deadlines(self, now:float|None=None):
        with self.lock:
            t=time.monotonic() if now is None else now
            for train in self.trains.values():
                if train.parked:continue
                if train.checkpoint_deadline is not None and t>train.checkpoint_deadline:
                    self.stop_all(f"train {train.train_id} missed {train.expected_checkpoint}")
                    break

    def park(self, train_id:int, stall:str):
        with self.lock:
            self.assert_motion_allowed()
            if stall not in STALLS: raise ValueError("invalid stall")
            track="1" if stall in ("1A","1B") else stall
            train=self.trains[train_id]
            train.velocity=0
            train.parked=stall
            self.yard_power[track]=False
            self.destinations["Yard "+stall]=train_id

    def snapshot(self):
        with self.lock:
            return {
                "mode":"simulation" if self.simulation else "hardware",
                "global_stop":self.global_stop,"stop_reason":self.stop_reason,
                "stop_causes":self.stop_causes.copy(),
                "controllers": self.controller_health.status() if self.controller_health else [],
                "estop_active":self.estop_active,
                "motion_armed":not self._rearm_required and not self.global_stop,
                "accessory_stop_faults":self.accessory_errors.copy(),
                "tipper":{"state":self.tipper,"fault":self.tipper_fault,"protected_zones":sorted(TIPPER_LOCKED)},
                "trains":[{"id":t.train_id,"name":t.name,"type":t.kind,"zone":t.zone,
                           "destination":t.destination,"cargo":t.cargo.value,"speed":t.velocity,
                           "parked":t.parked,"checkpoint":t.last_checkpoint,
                           "estimate_mm":t.estimate_mm,"cycle":t.cycle} for t in self.trains.values()],
                "zones":self.zones.copy(),"reservations":self.reservations.copy(),
                "turnouts":self.turnouts.copy(),"yard_power":self.yard_power.copy()
            }
