"""Conservative route planning derived from declared track topology."""
from __future__ import annotations

from dataclasses import dataclass
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
    required_feedback: tuple[str, ...] = ()
    unverified_segment: str | None = None


@dataclass(frozen=True)
class RoutePlan:
    train_id: int
    origin: str
    destination: str
    zones: tuple[str, ...]
    turnouts: tuple[tuple[str, str], ...]
    checkpoints: tuple[str, ...]
    required_controllers: tuple[str, ...]
    required_feedback: tuple[str, ...]
    status: RouteStatus
    blocking_reason: str | None = None
    blocking_segment: str | None = None


# No route is hardcoded here. Runtime route definitions come from the
# authoritative topology file. This default is intentionally empty until that
# file contains surveyed connections.
DEFAULT_ROUTES: tuple[RouteDefinition, ...] = ()


class RoutePlanner:
    def __init__(self, routes: Iterable[RouteDefinition] = DEFAULT_ROUTES):
        self.routes = tuple(routes)
        self._by_pair = {(route.origin, route.destination): route for route in self.routes}

    @classmethod
    def from_topology(cls, topology: dict) -> "RoutePlanner":
        """Build graph routes from verified declarative connections."""
        adjacency: dict[str, list[dict]] = {}
        for raw in topology.get("connections", []) or ():
            if not isinstance(raw, dict) or not raw.get("from") or not raw.get("to"):
                continue
            edge = dict(raw)
            edge["verified"] = bool(raw.get("verified", topology.get("verified", False)))
            adjacency.setdefault(str(raw["from"]), []).append(edge)
        routes: list[RouteDefinition] = []
        for origin in map(str, topology.get("origins", ()) or ()):
            for destination in map(str, topology.get("destinations", ()) or ()):
                path = cls._find_path(adjacency, origin, destination)
                if path:
                    routes.append(cls._definition_from_path(origin, destination, path))
        return cls(routes)

    @staticmethod
    def _find_path(adjacency: dict[str, list[dict]], origin: str, destination: str):
        queue = [(origin, [])]
        visited = {origin}
        while queue:
            node, path = queue.pop(0)
            if node == destination:
                return path
            for edge in adjacency.get(node, ()):
                target = str(edge["to"])
                if target not in visited:
                    visited.add(target)
                    queue.append((target, path + [edge]))
        return None

    @staticmethod
    def _definition_from_path(origin: str, destination: str, path: list[dict]) -> RouteDefinition:
        zones = tuple(str(edge["zone"]) for edge in path if edge.get("zone"))
        turnouts = tuple((str(edge["turnout"]), str(edge["position"]))
                    for edge in path if edge.get("turnout") and edge.get("position"))
        checkpoints = tuple(str(edge["checkpoint"]) for edge in path if edge.get("checkpoint"))
        controllers = tuple(sorted({str(item) for edge in path for item in edge.get("controllers", ())}))
        feedback = tuple(sorted({str(item) for edge in path for item in edge.get("feedback", ())}))
        unverified = next((str(edge.get("segment") or edge.get("zone") or
                                f"{edge['from']}->{edge['to']}")
                           for edge in path if not edge.get("verified")), None)
        return RouteDefinition(origin, destination, zones, turnouts, checkpoints,
                               controllers, all(bool(edge.get("verified")) for edge in path),
                               feedback, unverified)

    def plan(self, train_id: int, origin: str, destination: str, *, zones: dict,
             reservations: dict, controllers: dict[str, bool] | None = None,
             turnouts: dict[str, str | None] | None = None,
             destinations: dict[str, int | None] | None = None) -> RoutePlan:
        definition = self._by_pair.get((origin, destination))
        if definition is None:
            return RoutePlan(train_id, origin, destination, (), (), (), (), (),
                             RouteStatus.BLOCKED, "no approved route definition")
        if not definition.verified:
            segment = definition.unverified_segment
            reason = "route connection is not physically verified"
            if segment:
                reason += f": {segment}"
            return self._blocked(definition, train_id, reason, segment=segment)
        controllers = controllers or {}
        missing = [name for name in definition.required_controllers if not controllers.get(name, False)]
        if missing:
            return self._blocked(definition, train_id,
                                 "required controller unavailable: " + ", ".join(missing), RouteStatus.OFFLINE)
        for zone in definition.zones:
            if zone not in zones:
                return self._blocked(definition, train_id, f"unknown zone: {zone}", segment=zone)
            if zones[zone] not in (None, train_id) or reservations.get(zone) not in (None, train_id):
                return self._blocked(definition, train_id, f"zone occupied or reserved: {zone}", segment=zone)
        if destinations and destinations.get(destination) not in (None, train_id):
            return self._blocked(definition, train_id, "destination is occupied or reserved")
        for turnout, required in definition.turnouts:
            if (turnouts or {}).get(turnout) != required:
                return self._blocked(definition, train_id,
                                     f"turnout {turnout} lacks verified {required} alignment", segment=turnout)
        return RoutePlan(train_id, definition.origin, definition.destination, definition.zones,
                         definition.turnouts, definition.checkpoints, definition.required_controllers,
                         definition.required_feedback, RouteStatus.AVAILABLE)

    @staticmethod
    def _blocked(definition, train_id, reason, status=RouteStatus.BLOCKED, segment=None):
        return RoutePlan(train_id, definition.origin, definition.destination, definition.zones,
                         definition.turnouts, definition.checkpoints, definition.required_controllers,
                         definition.required_feedback, status, reason, segment)
