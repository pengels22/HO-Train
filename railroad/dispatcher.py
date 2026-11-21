"""Dispatcher and interlocks shared by simulation and Raspberry Pi hardware."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from threading import Event, RLock, Thread
import time
from typing import Callable
from railroad.routing.planner import RoutePlan, RoutePlanner, RouteStatus
from railroad.hardware.turnout_return import TurnoutAutoReturn

ZONES = tuple(f"{line}-{n}" for line in ("SKI", "FARM", "UND", "MINE", "MAIN") for n in (1, 2, 3))
STALLS = ("1A", "1B", "2", "3")
IR_LOCATION_MAP = {
    "Mine Station": ("Mine", None),
    "Farm Station": ("Farm", None),
    "Town Station": ("Town", None),
    "Ski Entrance": ("Ski", None),
    "Stall 1A": ("Yard · Stall 1A", "1A"),
    "Stall 1B": ("Yard · Stall 1B", "1B"),
    "Stall 2": ("Yard · Stall 2", "2"),
    "Stall 3": ("Yard · Stall 3", "3"),
    "Yard Entrance": ("Yard Entrance", None),
}
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
    location: str | None = None
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
    control_mode: str = "automatic"

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
    turnout_feedback: dict[str, str | None] = field(default_factory=lambda: {name: None for name in TURNOUT_DEFAULTS})
    yard_power: dict[str,bool] = field(default_factory=lambda: {"1":False,"2":False,"3":False})
    yard_power_verified: dict[str, bool] = field(default_factory=lambda: {"1":False,"2":False,"3":False})
    tipper: str = "IDLE"
    tipper_fault: str | None = None
    operator_mode: str = "dispatcher"
    dispatcher_running: bool = False
    cycle_requests: int = 0
    last_cycle_plan: dict | None = field(default=None, repr=False)
    cycle_state: str = "IDLE"
    cycle_fault: str | None = None
    cycle_train_id: int | None = None
    cycle_route: list[str] = field(default_factory=list)
    cycle_route_index: int = 0
    cycle_motion_command: Callable[[int, int], None] | None = field(default=None, repr=False)
    turnout_command: Callable[[str, str], None] | None = field(default=None, repr=False)
    turnout_auto_return: TurnoutAutoReturn | None = field(default=None, repr=False)
    route_planner: RoutePlanner = field(default_factory=RoutePlanner, repr=False)
    pending_requests: list[dict] = field(default_factory=list)
    request_history: list[dict] = field(default_factory=list)
    request_sequence: int = 0
    active_request_id: str | None = None
    yard_adapter: object | None = field(default=None, repr=False)
    _cycle_stop: Event | None = field(default=None, repr=False)
    _cycle_thread: Thread | None = field(default=None, repr=False)
    accessory_requests: dict[str, str] = field(default_factory=dict)
    global_stop: bool = False
    stop_reason: str | None = None
    stop_causes: dict[str, str] = field(default_factory=dict)
    simulation: bool = True
    motion_transport: object | None = field(default=None, repr=False)
    accessory_stops: dict[str, Callable[[], None]] = field(default_factory=dict, repr=False)
    motion_stops: list[Callable[[], None]] = field(default_factory=list, repr=False)
    accessory_errors: dict[str, str] = field(default_factory=dict, repr=False)
    controller_health: object | None = field(default=None, repr=False)
    _commanded_at: dict[int, float] = field(default_factory=dict, repr=False)
    speed_calibration: dict = field(default_factory=lambda: {"state": "IDLE"}, repr=False)
    _speed_calibration_timer: object | None = field(default=None, repr=False)
    # Calibrated physical velocity at full command, per locomotive. None means
    # the locomotive is not authorized for automatic slow-destination motion.
    speed_mm_s_at_255: dict[int, float | None] = field(default_factory=dict, repr=False)
    _rearm_required: bool = field(default=False, repr=False)
    lock: RLock = field(default_factory=RLock, repr=False)

    def attach_motion_transport(self, controller, *, require_rearm: bool = True) -> None:
        """Attach the sole hardware command gate.

        Simulation uses the dispatcher latch without a network sender. Hardware
        and bench runtimes attach ``LocomotiveCommandTransport`` explicitly at startup.
        """
        with self.lock:
            self.motion_transport = controller
            self._rearm_required = require_rearm

    def disarm(self) -> None:
        """Put the runtime behind the explicit rearm gate."""
        with self.lock:
            self._rearm_required = True

    def attach_accessory_stops(self, **stops: Callable[[], None]) -> None:
        """Register allow-listed tipper/turntable/accessory stop callbacks."""
        with self.lock:
            self.accessory_stops.update({k: v for k, v in stops.items() if v is not None})

    def attach_controller_health(self, registry) -> None:
        with self.lock:
            self.controller_health = registry
            registry.set_motion_provider(lambda: {
                train_id: abs(train.velocity) > 0
                for train_id, train in self.trains.items()
            })
            registry.set_command_provider(lambda: {
                train_id: {
                    "speed": int(train.velocity),
                    "direction": "forward" if train.velocity > 0 else "reverse" if train.velocity < 0 else "stopped",
                    "commanded_at": self._commanded_at.get(train_id),
                }
                for train_id, train in self.trains.items()
                if train_id in self._commanded_at
            })
            # A disconnected accessory or locomotive is reported in telemetry,
            # not treated as a stop command for every other train.
            registry.on_failure = None

    def attach_motion_stop(self, callback: Callable[[], None]) -> None:
        """Register a local motion engine stop hook.

        This is deliberately separate from accessory callbacks: a global stop
        must invalidate simulated targets before any later clock tick.
        """
        with self.lock:
            if callback not in self.motion_stops:
                self.motion_stops.append(callback)

    def attach_cycle_motion(self, callback: Callable[[int, int], None]) -> None:
        """Attach the approved motion writer used by an automatic-cycle adapter."""
        with self.lock:
            self.cycle_motion_command = callback

    def attach_turnout_command(self, callback: Callable[[str, str], None]) -> None:
        """Attach the open-loop turnout relay writer.

        A relay command selects NC/straight or NO/diverging. The dispatcher
        records the commanded alignment; no turnout feedback input is
        installed on this layout.
        """
        with self.lock:
            self.turnout_command = callback

    def enable_turnout_auto_return(self) -> None:
        """Opt-in dispatcher return tracker; still needs the real relay writer."""
        with self.lock:
            if self.turnout_command is None:
                raise SafetyError("turnout relay output is not connected")
            self.turnout_auto_return = TurnoutAutoReturn(self.turnout_command)

    def turnout_reed_event(self, sensor: str, *, closed: bool, now: float) -> None:
        """Forward stable Mega reed edges; never infer clearance from OPEN alone."""
        with self.lock:
            if self.turnout_auto_return is not None:
                self.turnout_auto_return.reed_event(sensor, closed=closed, now=now)

    def turnout_tail_confirmed(self, turnout: str, *, exit_reed: str) -> None:
        """Explicit rear-of-consist confirmation from the occupancy tracker."""
        with self.lock:
            if self.turnout_auto_return is not None:
                self.turnout_auto_return.confirm_tail_clear(turnout, exit_reed=exit_reed)

    def poll_turnout_returns(self, *, now: float, route_holds: set[str] | None = None,
                             occupied: set[str] | None = None,
                             connected: bool = False) -> tuple[str, ...]:
        """Caller must provide authoritative interlocks and live USB health."""
        with self.lock:
            if self.turnout_auto_return is None or self.global_stop:
                return ()
            result = self.turnout_auto_return.tick(
                now, route_holds=route_holds, occupied=occupied, connected=connected)
            for name in result:
                self.turnouts[name] = TURNOUT_DEFAULTS[name]
            return result

    @property
    def stop_transport_active(self) -> bool:
        return bool(self.motion_transport and self.motion_transport.active)

    @property
    def tipper_locked(self) -> bool:
        return self.tipper != "IDLE" or self.tipper_fault is not None

    def _cause_for_reason(self, reason: str) -> str:
        text = reason.lower()
        if "tipper" in text: return "tipper_fault"
        if "turntable" in text: return "turntable_fault"
        if "checkpoint" in text or "missed" in text or "unexpected" in text: return "checkpoint_fault"
        if "controller" in text or "communication" in text: return "controller_fault"
        if "operator" in text: return "operator_stop"
        return "safety_fault"

    def stop_all(self, reason: str, *, cause: str | None = None):
        with self.lock:
            self.global_stop = True
            self.stop_reason = self.stop_reason or reason
            self.stop_causes[cause or self._cause_for_reason(reason)] = reason
            self._rearm_required = True
            for t in self.trains.values():
                t.velocity = 0
                self._commanded_at[t.train_id] = time.monotonic()
            for stop in tuple(self.motion_stops):
                try:
                    stop()
                except Exception as exc:
                    self.accessory_errors["motion_engine"] = str(exc)
            if self.motion_transport:
                try:
                    self.motion_transport.activate()
                except Exception as exc:
                    self.accessory_errors["stop_transport"] = str(exc)
            for name, stop in self.accessory_stops.items():
                try:
                    stop()
                    self.accessory_errors.pop(name, None)
                except Exception as exc:
                    # Continue to UDP/other controllers even if one accessory
                    # controller is disconnected.
                    self.accessory_errors[name] = str(exc)

    def clear_stop(self):
        with self.lock:
            if any(t.expected_checkpoint and t.checkpoint_deadline and
                   time.monotonic() > t.checkpoint_deadline for t in self.trains.values()):
                raise SafetyError("unresolved checkpoint position fault")
            if "checkpoint_fault" in self.stop_causes:
                unresolved = any(t.expected_checkpoint for t in self.trains.values())
                if unresolved:
                    raise SafetyError("unresolved checkpoint position fault")
                self.stop_causes.pop("checkpoint_fault", None)
            for cause in ("operator_stop", "safety_fault"):
                self.stop_causes.pop(cause, None)
            if self.stop_causes:
                raise SafetyError("active stop causes remain: " + ", ".join(sorted(self.stop_causes)))
            self.global_stop = False
            self.stop_reason = None
            # Clearing the broadcast is not permission to move.  The explicit
            # rearm step below is intentionally separate.
            if self.motion_transport:
                self.motion_transport.clear()

    def rearm(self):
        """Explicitly rearm after an operator has reconciled the layout."""
        with self.lock:
            if self.global_stop:
                raise SafetyError("clear GLOBAL STOP before rearming")
            transaction = f"rearm-{time.monotonic_ns()}"
            if self.controller_health:
                self.controller_health.begin_rearm(transaction)
            if self.motion_transport:
                try:
                    self.motion_transport.rearm(transaction)
                except TypeError:
                    self.motion_transport.rearm()
            self._rearm_required = False

    def set_operator_mode(self, mode: str) -> None:
        mode = str(mode).lower()
        if mode not in {"dispatcher", "manual"}:
            raise SafetyError("operator mode must be dispatcher or manual")
        with self.lock:
            self.operator_mode = mode

    def enable_automatic(self) -> None:
        """Explicitly enable automatic scheduling; it never starts a cycle."""
        with self.lock:
            self.operator_mode = "dispatcher"
            self.dispatcher_running = True

    def disable_automatic(self) -> None:
        with self.lock:
            self.dispatcher_running = False

    def manual_takeover(self, train_id: int) -> None:
        """Suspend automatic control for one train and issue an individual STOP."""
        with self.lock:
            if train_id not in self.trains:
                raise KeyError(train_id)
            self.trains[train_id].control_mode = "manual"
            self.trains[train_id].velocity = 0
            self.stop_train(train_id)

    def set_turnout_feedback(self, turnout: str, position: str | None) -> None:
        """Accept an optional legacy turnout feedback event if one is provided."""
        if turnout not in self.turnout_feedback:
            raise KeyError(turnout)
        if position not in {None, "straight", "diverging"}:
            raise ValueError("turnout feedback must be straight, diverging, or None")
        with self.lock:
            self.turnout_feedback[turnout] = position

    def plan_route(self, train_id: int, origin: str, destination: str) -> RoutePlan:
        with self.lock:
            controller_status = {}
            if self.controller_health:
                for item in self.controller_health.status(moving_locomotives={}):
                    controller_status[str(item.get("id"))] = bool(item.get("connected"))
            controller_status["tipper"] = bool(controller_status.get("tipper"))
            controller_status["turntable"] = bool(controller_status.get("turntable"))
            return self.route_planner.plan(train_id, origin, destination,
                                           zones=self.zones, reservations=self.reservations,
                                           controllers=controller_status,
                                           turnouts=self.turnouts,
                                           destinations=self.destinations)

    def submit_request(self, train_id: int, destination: str, *,
                       origin: str | None = None, priority: int = 0) -> dict:
        with self.lock:
            if train_id not in self.trains:
                raise KeyError(train_id)
            if any(item["train_id"] == train_id and item["state"] in
                   {"PENDING", "PLANNING", "BLOCKED", "READY", "RUNNING"}
                   for item in self.pending_requests):
                raise SafetyError(f"train {train_id} already has an active request")
            self.assign_destination(train_id, destination)
            self.request_sequence += 1
            request = {"request_id": f"req-{self.request_sequence}", "train_id": train_id,
                       "origin": origin if origin is not None else (self.trains[train_id].zone or self.trains[train_id].parked or ""),
                       "destination": destination, "submitted_at": time.time(),
                       "priority": int(priority),
                       "state": "PENDING", "planned_route": None, "blocking_reason": None,
                       "result": None}
            self.pending_requests.append(request)
            self.request_history.append(request.copy())
            return request.copy()

    def cancel_request(self, train_id: int) -> bool:
        with self.lock:
            for item in self.pending_requests:
                if item["train_id"] == train_id and item["state"] in {"PENDING", "BLOCKED", "READY"}:
                    item["state"] = "CANCELLED"
                    item["result"] = "cancelled by operator"
                    self._update_request_history(item)
                    return True
            return False

    def _update_request_history(self, request: dict) -> None:
        for index, old in enumerate(self.request_history):
            if old["request_id"] == request["request_id"]:
                self.request_history[index] = request.copy()
                return

    def start_dispatcher(self) -> None:
        with self.lock:
            self.dispatcher_running = True
            if self._cycle_thread is None:
                self._cycle_stop = Event()
                self._cycle_thread = Thread(target=self._dispatcher_loop, name="ho-dispatcher", daemon=True)
                self._cycle_thread.start()

    def stop_dispatcher(self) -> None:
        with self.lock:
            self.dispatcher_running = False
            if self._cycle_stop is not None:
                self._cycle_stop.set()
            thread = self._cycle_thread
            self._cycle_thread = None
        if thread is not None:
            thread.join(timeout=1.0)

    def _dispatcher_loop(self):
        while self._cycle_stop is not None and not self._cycle_stop.wait(0.1):
            with self.lock:
                active = self.dispatcher_running
                if self.cycle_state == "COMPLETED":
                    self.cycle_state = "IDLE"
            if active and self.cycle_state == "IDLE":
                try:
                    self.run_cycle_once()
                except Exception as exc:
                    with self.lock:
                        self.cycle_state = "FAULT"
                        self.cycle_fault = str(exc)

    def run_cycle_once(self) -> None:
        """Plan one eligible cycle without issuing a hardware motion command.

        Planning is deliberately separate from actuation: route reservations
        and physical sensor verification must be supplied before a command
        writer may move a locomotive.
        """
        with self.lock:
            self.cycle_requests += 1
            active_requests = [item for item in self.pending_requests
                               if item["state"] in {"PENDING", "BLOCKED"}]
            active_requests.sort(key=lambda item: (-int(item.get("priority", 0)),
                                                   float(item.get("submitted_at", 0)), item["request_id"]))
            selected_request = None
            eligible = None
            for item in active_requests:
                train = self.trains.get(item["train_id"])
                if train is None or train.control_mode != "automatic":
                    continue
                if not self.simulation:
                    proposal = self.plan_route(item["train_id"], item["origin"], item["destination"])
                    if proposal.status is not RouteStatus.AVAILABLE:
                        item["state"] = "BLOCKED"
                        item["blocking_reason"] = proposal.blocking_reason
                        item["planned_route"] = proposal.__dict__
                        self._update_request_history(item)
                        continue
                selected_request, eligible = item, train
                break
            if eligible is None:
                eligible = next((t for t in self.trains.values()
                                 if t.control_mode == "automatic" and t.destination and not t.parked), None)
            if selected_request:
                selected_request["state"] = "PLANNING"
                self.active_request_id = selected_request["request_id"]
                self._update_request_history(selected_request)
            if eligible is None:
                self.cycle_state = "IDLE"
                self.last_cycle_plan = {"state": "IDLE", "reason": "no eligible train"}
                return
            self.cycle_train_id = eligible.train_id
            self.cycle_fault = None
            self.cycle_state = "PLANNING"
            plan = None
            if not self.simulation:
                origin = eligible.zone or ("Yard" if eligible.parked else "")
                plan = self.plan_route(eligible.train_id, origin, eligible.destination or "")
                if plan.status is not RouteStatus.AVAILABLE:
                    self.cycle_state = "BLOCKED"
                    self.cycle_fault = plan.blocking_reason or plan.status.value
                    if selected_request:
                        selected_request["state"] = "BLOCKED"
                        selected_request["blocking_reason"] = self.cycle_fault
                        self._update_request_history(selected_request)
                    self.last_cycle_plan = {"state": self.cycle_state, "train": eligible.train_id,
                                            "reason": self.cycle_fault, "route_status": plan.status.value}
                    return
                route = list(plan.zones)
            else:
                route = self._cycle_route_for(eligible)
            if not route or not self.route_available(eligible.train_id, route):
                self.cycle_state = "BLOCKED"
                self.cycle_fault = "required route unavailable or protected"
                if selected_request:
                    selected_request["state"] = "BLOCKED"
                    selected_request["blocking_reason"] = self.cycle_fault
                    self._update_request_history(selected_request)
                self.last_cycle_plan = {"state": self.cycle_state, "train": eligible.train_id,
                                        "reason": self.cycle_fault}
                return
            # Reservation and alignment are one protected planning step.  A
            # route is never exposed as READY until every requested turnout is
            # physically confirmed or the operation is rejected.
            if plan is not None:
                try:
                    self._align_turnouts(plan)
                    self._authorize_hardware_motion(eligible.train_id)
                except SafetyError as exc:
                    self.cycle_state = "BLOCKED"
                    self.cycle_fault = str(exc)
                    if selected_request:
                        selected_request["state"] = "BLOCKED"
                        selected_request["blocking_reason"] = self.cycle_fault
                        selected_request["planned_route"] = plan.__dict__
                        self._update_request_history(selected_request)
                    self.last_cycle_plan = {"state": self.cycle_state, "train": eligible.train_id,
                                            "reason": self.cycle_fault}
                    return
            # `reserve` performs the complete check and write while holding
            # the dispatcher lock, including the destination reservation.
            self.reserve(eligible.train_id, route, eligible.destination)
            self.cycle_route = route
            self.cycle_route_index = 0
            self.cycle_state = "READY"
            if selected_request:
                selected_request["state"] = "READY"
                selected_request["planned_route"] = {
                    **plan.__dict__, "zones": list(route),
                    "turnouts": list(plan.turnouts), "checkpoints": list(plan.checkpoints),
                    "required_feedback": list(plan.required_feedback),
                    "status": plan.status.value if plan else "READY",
                } if plan is not None else {"zones": list(route), "status": "READY"}
                self._update_request_history(selected_request)
            eligible.expected_checkpoint = route[0]
            eligible.checkpoint_deadline = time.monotonic() + 30.0
            motion_issued = False
            if self.simulation and self.cycle_motion_command is not None:
                self.cycle_motion_command(eligible.train_id, 64)
                eligible.velocity = 64
                motion_issued = True
            elif plan is not None:
                # The hardware transport is the only production motion path.
                self.command_motion(eligible.train_id, 64)
                motion_issued = True
                if selected_request:
                    selected_request["state"] = "RUNNING"
                    self._update_request_history(selected_request)
            self.last_cycle_plan = {"state": self.cycle_state, "train": eligible.train_id,
                                    "origin": eligible.zone, "destination": eligible.destination,
                                    "route": route,
                                    "motion_issued": motion_issued,
                                    "reason": "awaiting verified checkpoint and controller events"}

    def _align_turnouts(self, plan: RoutePlan) -> None:
        """Command missing turnout alignments and record the relay assumption."""
        for turnout, required in plan.turnouts:
            current = self.turnouts.get(turnout)
            if current == required:
                continue
            if self.turnout_auto_return is not None:
                self.turnout_auto_return.command_position(turnout, required)
            elif self.turnout_command is not None:
                self.turnout_command(turnout, required)
            self.turnouts[turnout] = required

    def _authorize_hardware_motion(self, train_id: int) -> None:
        if self.motion_transport is None:
            raise SafetyError("locomotive motion transport is unavailable")
        if self.controller_health is None or not self.controller_health.operating_ready(train_id):
            raise SafetyError(f"locomotive {train_id} is not communication-ready")

    def _cycle_route_for(self, train: Train) -> list[str]:
        routes = {"Mine": ["MAIN-2", "MINE-1"], "Farm": ["MAIN-2", "FARM-1"],
                  "Ski": ["MAIN-1", "SKI-1"], "Town": ["MAIN-1", "MAIN-2"],
                  "Tipper": ["MAIN-2", "MAIN-3"], "Turntable": ["MAIN-1"],
                  "Yard": ["MAIN-1"]}
        return list(routes.get(train.destination or "", ()))

    def cycle_checkpoint(self, receiver: str, *, zone: str | None = None,
                         last_car_confirmed: bool = False, now: float | None = None):
        """Advance an active cycle from an actual receiver event."""
        with self.lock:
            if self.cycle_state not in {"READY", "MOVING", "ARRIVING"} or self.cycle_train_id is None:
                raise SafetyError("no active automatic cycle")
            train = self.trains[self.cycle_train_id]
            self.cycle_state = "MOVING"
            self.checkpoint(train.train_id, receiver, zone=zone, now=now)
            if zone in self.cycle_route and last_car_confirmed:
                self.zones[zone] = None
                self.reservations[zone] = None
            self.cycle_route_index += 1
            if self.cycle_route_index < len(self.cycle_route):
                train.expected_checkpoint = self.cycle_route[self.cycle_route_index]
                train.checkpoint_deadline = (time.monotonic() if now is None else now) + 30.0
            if self.cycle_route_index >= len(self.cycle_route):
                self.cycle_state = "COMPLETED"
                if self.active_request_id:
                    for request in self.pending_requests:
                        if request["request_id"] == self.active_request_id:
                            request["state"] = "COMPLETED"
                            request["result"] = "arrival and clearance confirmed"
                            self._update_request_history(request)
                            break
                    self.active_request_id = None
                if self.cycle_motion_command is not None:
                    self.cycle_motion_command(train.train_id, 0)
                train.velocity = 0
                self.cycle_train_id = None
                self.cycle_route = []
            else:
                self.cycle_state = "ARRIVING"

    def set_train_mode(self, train_id: int, mode: str) -> None:
        mode = str(mode).lower()
        if mode not in {"manual", "automatic"}:
            raise SafetyError("train mode must be manual or automatic")
        with self.lock:
            self.trains[train_id].control_mode = mode

    def set_yard_power(self, track: str, enabled: bool) -> None:
        track = str(track)
        if track not in self.yard_power:
            raise SafetyError(f"unknown yard track: {track}")
        with self.lock:
            if self.yard_adapter is not None:
                self.yard_adapter.set_power(track, enabled)
            self.yard_power[track] = bool(enabled)

    def clear_yard_assignments(self) -> None:
        with self.lock:
            for train in self.trains.values():
                train.parked = None

    def record_accessory_request(self, accessory: str, command: str) -> None:
        with self.lock:
            self.accessory_requests[str(accessory)] = str(command)

    def command_motion(self, train_id: int, speed: int) -> None:
        """Set a commanded speed through the dispatcher stop gate.

        This is the dispatcher-facing path for hardware command writers; it
        cannot issue a nonzero command while stopped, latched, or disarmed.
        """
        with self.lock:
            self.assert_motion_allowed(train_id)
            if train_id not in self.trains:
                raise KeyError(train_id)
            self._enforce_destination_speed(train_id, speed)
            if not self.simulation and speed and self.motion_transport is None:
                raise SafetyError("locomotive motion transport is unavailable")
            if self.motion_transport:
                self.motion_transport.send_motion(train_id, speed)
            self.trains[train_id].velocity = int(speed)
            self._commanded_at[train_id] = time.monotonic()

    def stop_train(self, train_id: int) -> None:
        """Issue a zero-speed command without requiring a movement arm gate."""
        with self.lock:
            if train_id not in self.trains:
                raise KeyError(train_id)
            if self.motion_transport:
                self.motion_transport.send_motion(train_id, 0)
            self.trains[train_id].velocity = 0
            self._commanded_at[train_id] = time.monotonic()

    def set_speed_calibration(self, train_id: int, mm_s_at_255: float | None) -> None:
        """Set measured full-command speed; null deliberately disables unknown hardware."""
        if mm_s_at_255 is not None and mm_s_at_255 <= 0:
            raise ValueError("calibrated speed must be positive")
        self.speed_mm_s_at_255[train_id] = mm_s_at_255

    def arm_speed_calibration(self, train_id: int, start_receiver: str,
                              end_receiver: str, distance_mm: float = 914.4,
                              stop_delay_ms: int = 1000,
                              turnout_c_straight_confirmed: bool = False) -> dict:
        """Arm a measured two-receiver full-speed run; does not start motion."""
        if train_id not in self.trains:
            raise KeyError(train_id)
        if not start_receiver or not end_receiver or start_receiver == end_receiver:
            raise ValueError("calibration requires two different receivers")
        if distance_mm <= 0 or stop_delay_ms < 0:
            raise ValueError("calibration distance and stop delay must be positive")
        with self.lock:
            if self.speed_calibration.get("state") in {"ARMED", "TIMING", "STOP_PENDING"}:
                raise SafetyError("speed calibration is already active")
            alignment_source = self._ensure_turnout_alignment(
                "C", "straight", operator_confirmed=turnout_c_straight_confirmed)
            self.speed_calibration = {
                "state": "ARMED", "train_id": train_id,
                "start_receiver": start_receiver, "end_receiver": end_receiver,
                "distance_mm": float(distance_mm), "stop_delay_ms": int(stop_delay_ms),
                "started_at": None, "ended_at": None, "elapsed_s": None,
                "speed_mm_s": None, "speed_mm_s_at_255": None,
                "required_turnouts": {"C": "straight"},
                "turnout_alignment_source": alignment_source,
                "error": None,
            }
            return dict(self.speed_calibration)

    def _ensure_turnout_alignment(self, turnout: str, required: str, *, operator_confirmed: bool = False) -> str:
        if self.turnout_auto_return is not None:
            self.turnout_auto_return.command_position(turnout, required)
        elif self.turnout_command is not None:
            self.turnout_command(turnout, required)
        self.turnouts[turnout] = required
        return "relay_command_assumed"

    def cancel_speed_calibration(self) -> dict:
        with self.lock:
            if self._speed_calibration_timer is not None:
                self._speed_calibration_timer.cancel()
                self._speed_calibration_timer = None
            self.speed_calibration = {"state": "IDLE"}
            return dict(self.speed_calibration)

    def _handle_speed_calibration_event(self, event) -> bool:
        """Consume matching receiver edges and calculate commanded speed."""
        with self.lock:
            calibration = self.speed_calibration
            if event.train_id != calibration.get("train_id"):
                return False
            receiver = event.receiver_id
            if calibration.get("state") == "ARMED" and receiver == calibration.get("start_receiver"):
                command_speed = abs(self.trains[event.train_id].velocity)
                if command_speed <= 0:
                    calibration["error"] = "train must be moving at the start receiver"
                    return True
                calibration.update({"state": "TIMING", "started_at": event.timestamp,
                                    "command_speed": command_speed})
                return True
            if calibration.get("state") != "TIMING" or receiver != calibration.get("end_receiver"):
                return False
            elapsed = event.timestamp - float(calibration["started_at"])
            if elapsed <= 0:
                calibration["state"] = "ERROR"
                calibration["error"] = "receiver timestamps are not monotonic"
                return True
            measured = float(calibration["distance_mm"]) / elapsed
            command_speed = max(1, int(calibration.get("command_speed", 255)))
            normalized = measured * 255.0 / command_speed
            calibration.update({"state": "STOP_PENDING", "ended_at": event.timestamp,
                                "elapsed_s": elapsed, "speed_mm_s": measured,
                                "speed_mm_s_at_255": normalized})
            train_id = event.train_id
            delay = int(calibration["stop_delay_ms"]) / 1000.0
            def finish():
                try:
                    self.stop_train(train_id)
                    with self.lock:
                        self.set_speed_calibration(train_id, normalized)
                        self.speed_calibration["state"] = "COMPLETE"
                except Exception as exc:
                    with self.lock:
                        self.speed_calibration["state"] = "ERROR"
                        self.speed_calibration["error"] = str(exc)
                finally:
                    self._speed_calibration_timer = None
            from threading import Timer
            self._speed_calibration_timer = Timer(delay, finish)
            self._speed_calibration_timer.daemon = True
            self._speed_calibration_timer.start()
            return True

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
            raise SafetyError("motion command blocked by dispatcher stop/disarmed state")
        if not self.simulation and train_id is not None:
            self._authorize_hardware_motion(train_id)

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
                # Record the tipper fault locally. Other trains/accessories run normally.

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
        """Plan a destination without authorizing or commanding movement.

        Planning remains available during a global stop or before hardware
        rearm.  Motion and accessory commands continue to use the safety gate.
        """
        with self.lock:
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
                    self.set_tipper("FAULT", "tipper failed and train unsafe to depart")
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
        location, stall = IR_LOCATION_MAP.get(event.receiver_id, (event.receiver_id, None))
        with self.lock:
            train = self.trains[event.train_id]
            train.location = location
            train.parked = stall
            if stall is not None:
                train.zone = "YARD"
            self._handle_speed_calibration_event(event)
            self.checkpoint(event.train_id, event.receiver_id, zone=zone, now=event.timestamp)
        return location

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
            moving_locomotives = {train_id: abs(train.velocity) > 0
                                  for train_id, train in self.trains.items()}
            return {
                "mode":"simulation" if self.simulation else "hardware",
                "operator_mode": self.operator_mode,
                "dispatcher_running": self.dispatcher_running,
                "cycle_requests": self.cycle_requests,
                "last_cycle_plan": self.last_cycle_plan.copy() if self.last_cycle_plan else None,
                "cycle_state": self.cycle_state,
                "cycle_fault": self.cycle_fault,
                "global_stop":self.global_stop,"stop_reason":self.stop_reason,
                "stop_causes":self.stop_causes.copy(),
                "controllers": (self.controller_health.status(moving_locomotives=moving_locomotives)
                                if self.controller_health else []),
                "stop_transport_active":self.stop_transport_active,
                "motion_armed":not self._rearm_required and not self.global_stop,
                "speed_calibration": self.speed_calibration.copy(),
                "speed_calibrations_mm_s_at_255": self.speed_mm_s_at_255.copy(),
                "accessory_stop_faults":self.accessory_errors.copy(),
                "tipper":{"state":self.tipper,"fault":self.tipper_fault,"protected_zones":sorted(TIPPER_LOCKED)},
                "trains":[{"id":t.train_id,"name":t.name,"type":t.kind,"zone":t.zone,
                           "location":t.location,
                           "destination":t.destination,"cargo":t.cargo.value,"speed":t.velocity,
                           "mode":t.control_mode,
                           "parked":t.parked,"checkpoint":t.last_checkpoint,
                           "estimate_mm":t.estimate_mm,"cycle":t.cycle} for t in self.trains.values()],
                "zones":self.zones.copy(),"reservations":self.reservations.copy(),
                "turnouts":self.turnouts.copy(),"yard_power":self.yard_power.copy(),
                "turnout_feedback": self.turnout_feedback.copy(),
                "pending_requests": [item.copy() for item in self.pending_requests],
                "request_history": [item.copy() for item in self.request_history],
                "active_request_id": self.active_request_id,
                "yard_power_requested": self.yard_power.copy(),
                "yard_power_verified": self.yard_power_verified.copy(),
                "yard_power_hardware": self.yard_adapter.status() if self.yard_adapter else None,
                "accessory_requests":self.accessory_requests.copy()
            }
