from pathlib import Path
from typing import Any
import yaml
from railroad.routing.zones import Zone, ZoneEngine

def load_zones(path: str | Path) -> ZoneEngine:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
    zones = {}
    for item in data.get("zones", []):
        zones[item["id"]] = Zone(
            zone_id=item["id"], railway=item["railway"], color=item["color"],
            segments=tuple(item.get("segments", [])), entrances=tuple(item.get("entrances", [])),
            exits=tuple(item.get("exits", [])), neighbors=tuple(item.get("neighbors", [])),
            elevation=item.get("elevation"), hall_sensors=tuple(item.get("hall_sensors", [])),
            ir_checkpoints=tuple(item.get("ir_checkpoints", [])), turnouts=tuple(item.get("turnouts", [])),
            verified=bool(item.get("verified", False)),
        )
    engine = ZoneEngine(zones)
    errors = engine.validate()
    if errors:
        raise ValueError("invalid zone configuration: " + "; ".join(errors))
    return engine
