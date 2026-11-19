"""Conservative, declarative route planning for the Phase 2 dispatcher.

This module contains no hardware drivers and never infers sensor state.  Route
definitions are deliberately marked unverified until the surveyed layout and
feedback assignments are commissioned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class RouteStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    OFFLINE = "OFFLINE"
    FAULTED = "FAULTED"


@dataclass(frozen=True)
class RouteDefinition:
    origin: str
    destination: str
    zones: tuple[str, ...]
    turnouts: tuple[tuple[str, str], ...] = ()
    checkpoints: tuple[str, ...] = ()
    required_controllers: tuple[str, ...] = ()
    verified: bool = False


@dataclass(frozen=True)
class RoutePlan:
    train_id: int
    origin: str
    destination: str
    zones: tuple[str, ...]
    turnouts: tuple[tuple[str, str], ...]
    checkpoints: tuple[str, ...]
    required_controllers: tuple[str, ...]
    status: RouteStatus
    blocking_reason: str | None = None


# Only the explicitly documented turnout relationships are represented here.
# The definitions remain unverified until the physical route is commissioned.
DEFAULT_ROUTES = (
    RouteDefinition("Yard", "Mine", ("MAIN-2", "MAIN-3", "UND-1", "UND-2", "UND-3", "MINE-1"),
                    (("A", "straight"), ("D", "diverging"), ("E", "diverging"), ("F", "straight")),
                    ("yard_entrance", "tunnel_exit_west")),
    RouteDefinition("Yard", "Farm", ("MAIN-1", "FARM-1"), (("C", "straight"),), ("yard_entrance",)),
    RouteDefinition("Yard", "Ski", ("MAIN-1", "SKI-1"), (("C", "diverging"),), ("ski_entrance",)),
    RouteDefinition("Yard", "Town", ("MAIN-1",), (("G", "straight"),), ("yard_entrance",)),
    RouteDefinition("Yard", "Tipper", ("MAIN-2", "MAIN-3"), (("D", "diverging"), ("E", "diverging")),
                    ("tipper_entrance",), ("tipper",)),
    RouteDefinition("Yard", "Turntable", ("MAIN-1",), (), ("yard_entrance",), ("turntable",)),
)


class RoutePlanner:
    def __init__(self, routes: Iterable[RouteDefinition] = DEFAULT_ROUTES):
        self.routes = tuple(routes)
        self._by_pair = {(route.origin, route.destination): route for route in self.routes}

    def plan(self, train_id: int, origin: str, destination: str, *, zones: dict,
             reservations: dict, controllers: dict[str, bool] | None = None,
             turnouts: dict[str, str | None] | None = None,
             destinations: dict[str, int | None] | None = None) -> RoutePlan:
        definition = self._by_pair.get((origin, destination))
        if definition is None:
            return RoutePlan(train_id, origin, destination, (), (), (), (),
                             RouteStatus.BLOCKED, "no approved route definition")
        if not definition.verified:
            return self._blocked(definition, train_id, "route topology is not physically verified")
        controllers = controllers or {}
        missing = [name for name in definition.required_controllers if not controllers.get(name, False)]
        if missing:
            return self._blocked(definition, train_id, "required controller unavailable: " + ", ".join(missing), RouteStatus.OFFLINE)
        for zone in definition.zones:
            if zone not in zones:
                return self._blocked(definition, train_id, f"unknown zone: {zone}")
            if zones[zone] not in (None, train_id) or reservations.get(zone) not in (None, train_id):
                return self._blocked(definition, train_id, f"zone occupied or reserved: {zone}")
        if destinations and destinations.get(destination) not in (None, train_id):
            return self._blocked(definition, train_id, "destination is occupied or reserved")
        for turnout, required in definition.turnouts:
            actual = (turnouts or {}).get(turnout)
            if actual != required:
                return self._blocked(definition, train_id, f"turnout {turnout} lacks verified {required} alignment")
        return RoutePlan(train_id, definition.origin, definition.destination, definition.zones,
                         definition.turnouts, definition.checkpoints, definition.required_controllers,
                         RouteStatus.AVAILABLE)

    @staticmethod
    def _blocked(definition, train_id, reason, status=RouteStatus.BLOCKED):
        return RoutePlan(train_id, definition.origin, definition.destination, definition.zones,
                         definition.turnouts, definition.checkpoints, definition.required_controllers,
                         status, reason)
