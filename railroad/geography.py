"""Authoritative overlay geography and the single image-coordinate transform."""
from __future__ import annotations

from pathlib import Path
import yaml

CLEAN_WIDTH, CLEAN_HEIGHT = 752.0, 602.0
DESIGN_WIDTH, DESIGN_HEIGHT = 739.0, 593.0


def source_pixel_to_clean_normalized(point: list[float] | tuple[float, float]) -> list[float]:
    """Transform v05 cropped-design pixels into clean-image normalized space.

    The recovered v05 design is already in the cropped layout coordinate
    space, so this is intentionally a scale-only transform with no crop
    offset.
    """
    x, y = map(float, point)
    return [x / DESIGN_WIDTH, y / DESIGN_HEIGHT]


def clean_normalized_to_source_pixel(point: list[float] | tuple[float, float]) -> list[float]:
    x, y = map(float, point)
    return [x * DESIGN_WIDTH, y * DESIGN_HEIGHT]


def _position(value):
    if value is None:
        return None
    return [float(value[0]), float(value[1])]


def load_geography(root: Path) -> dict:
    boundaries = yaml.safe_load((root / "config/zone_boundaries.yaml").read_text()) or {}
    design = yaml.safe_load((root / "config/geography_design_v05.yaml").read_text()) or {}
    track = yaml.safe_load((root / "config/track_layout.yaml").read_text()) or {}
    ir = yaml.safe_load((root / "config/ir_receivers.yaml").read_text()) or {}
    zones = {}
    for zone_id, data in (boundaries.get("boundaries", {}) or {}).items():
        zones[zone_id] = {"start": _position(data.get("start")), "end": _position(data.get("end")),
                          "calibrated": bool(data.get("calibrated", False))}
    receivers = []
    design_receivers = design.get("receivers", {})
    for receiver in ir.get("receivers", []):
        source = design_receivers.get(receiver["id"], {})
        receivers.append({"id": receiver["id"], "name": receiver.get("description", receiver["id"]),
                          "channel": receiver.get("channel"), "zones": receiver.get("zones", []),
                          "position": _position(source.get("position")),
                          "calibrated": bool(source.get("verified", False))})
    turnouts = {}
    design_turnouts = design.get("turnouts", {})
    for turnout_id, data in (track.get("powered_turnouts", {}) or {}).items():
        source = design_turnouts.get(turnout_id, {})
        turnouts[turnout_id] = {**data, "position": _position(source.get("position")),
                                "calibrated": bool(source.get("verified", False))}
    return {"coordinate_system": "clean_image_normalized_0_to_1",
            "image": {"path": "/dashboard/images/railroad-layout-clean.png", "width": int(CLEAN_WIDTH), "height": int(CLEAN_HEIGHT),
                      "source_image": design.get("source_image", "railroad-map-exact.png"),
                      "source_width": int(DESIGN_WIDTH), "source_height": int(DESIGN_HEIGHT),
                      "crop_offset": [0, 0],
                      "coordinate_transform": "scale only; source is already cropped"},
            "design_verified": bool((design.get("meta") or {}).get("verified", design.get("verified", False))),
            "zones": zones, "ir_receivers": receivers, "turnouts": turnouts}
