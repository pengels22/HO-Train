"""Authoritative overlay geography and the single image-coordinate transform."""
from __future__ import annotations

from pathlib import Path
import yaml

CLEAN_WIDTH, CLEAN_HEIGHT = 752.0, 602.0
CROP_OFFSET_X, CROP_OFFSET_Y = 469.0, 205.0
SOURCE_WIDTH, SOURCE_HEIGHT = 1559.0, 1009.0


def source_pixel_to_clean_normalized(point: list[float] | tuple[float, float]) -> list[float]:
    """Transform an original screenshot pixel into clean-image normalized space."""
    x, y = map(float, point)
    return [(x - CROP_OFFSET_X) / CLEAN_WIDTH, (y - CROP_OFFSET_Y) / CLEAN_HEIGHT]


def clean_normalized_to_source_pixel(point: list[float] | tuple[float, float]) -> list[float]:
    x, y = map(float, point)
    return [x * CLEAN_WIDTH + CROP_OFFSET_X, y * CLEAN_HEIGHT + CROP_OFFSET_Y]


def _position(value):
    if value is None:
        return None
    return [float(value[0]), float(value[1])]


def load_geography(root: Path) -> dict:
    boundaries = yaml.safe_load((root / "config/zone_boundaries.yaml").read_text()) or {}
    track = yaml.safe_load((root / "config/track_layout.yaml").read_text()) or {}
    ir = yaml.safe_load((root / "config/ir_receivers.yaml").read_text()) or {}
    zones = {}
    for zone_id, data in (boundaries.get("boundaries", {}) or {}).items():
        zones[zone_id] = {"start": _position(data.get("start")), "end": _position(data.get("end")),
                          "calibrated": bool(data.get("calibrated", False))}
    receivers = []
    for receiver in ir.get("receivers", []):
        receivers.append({"id": receiver["id"], "name": receiver.get("description", receiver["id"]),
                          "channel": receiver.get("channel"), "zones": receiver.get("zones", []),
                          "position": _position(receiver.get("position")),
                          "calibrated": bool(receiver.get("calibrated", False))})
    turnouts = {}
    for turnout_id, data in (track.get("powered_turnouts", {}) or {}).items():
        turnouts[turnout_id] = {**data, "position": _position(data.get("position")),
                                "calibrated": bool(data.get("calibrated", False))}
    return {"coordinate_system": "clean_image_normalized_0_to_1",
            "image": {"path": "/dashboard/images/railroad-layout-clean.png", "width": int(CLEAN_WIDTH), "height": int(CLEAN_HEIGHT),
                      "source_width": int(SOURCE_WIDTH), "source_height": int(SOURCE_HEIGHT),
                      "crop_offset": [int(CROP_OFFSET_X), int(CROP_OFFSET_Y)]},
            "zones": zones, "ir_receivers": receivers, "turnouts": turnouts}
