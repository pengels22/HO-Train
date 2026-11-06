"""Authoritative overlay geography and the single image-coordinate transform."""
from __future__ import annotations

from pathlib import Path
import yaml
from railroad.track_geometry import load_centerlines, point_at_distance, project_point, normalized_projection, validate_graph

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


def _project(geometry, path_id, raw_position, record=None):
    record = record or {}
    if record.get("segment_id") and record.get("distance_px") is not None:
        point = point_at_distance(geometry, record["segment_id"], record["distance_px"])
        return {"track_path": path_id, "segment_id": record["segment_id"], "distance_px": float(record["distance_px"]),
                "position": [point[0] / CLEAN_WIDTH, point[1] / CLEAN_HEIGHT],
                "alignment_error_px": float(record.get("alignment_error_px", 0.0))}
    if raw_position is None:
        return None
    raw = [float(raw_position[0]) * CLEAN_WIDTH, float(raw_position[1]) * CLEAN_HEIGHT]
    return normalized_projection(project_point(geometry, path_id, raw, record.get("segment_id")), CLEAN_WIDTH, CLEAN_HEIGHT)


def load_geography(root: Path) -> dict:
    boundaries = yaml.safe_load((root / "config/zone_boundaries.yaml").read_text()) or {}
    design = yaml.safe_load((root / "config/geography_design_v05.yaml").read_text()) or {}
    geometry = load_centerlines(root)
    marker_geometry = yaml.safe_load((root / "config/marker_geometry_v05.yaml").read_text()) or {}
    imported = geometry.get("source_format", "").startswith("JMRI")
    zone_geometry = marker_geometry.get("zone_endpoints", {}) or {}
    track = yaml.safe_load((root / "config/track_layout.yaml").read_text()) or {}
    reconciliation = yaml.safe_load((root / "config/jmri_turnout_reconciliation.yaml").read_text()) or {} if (root / "config/jmri_turnout_reconciliation.yaml").exists() else {}
    ir = yaml.safe_load((root / "config/ir_receivers.yaml").read_text()) or {}
    zones = {}
    for zone_id, data in (boundaries.get("boundaries", {}) or {}).items():
        path_id = zone_id.split("-")[0].replace("UND", "Underground").title()
        if path_id == "Ski": path_id = "Ski"
        elif path_id == "Farm": path_id = "Farm"
        elif path_id == "Mine": path_id = "Mine"
        elif path_id == "Main": path_id = "Main"
        elif path_id == "Underground": path_id = "Underground"
        association = zone_geometry.get(zone_id, {})
        projection_path = "JMRI" if imported else path_id
        start_record = {} if imported else {"segment_id": association.get("start")}
        end_record = {} if imported else {"segment_id": association.get("end")}
        start = _project(geometry, projection_path, data.get("start"), start_record) if data.get("start") else None
        end = _project(geometry, projection_path, data.get("end"), end_record) if data.get("end") else None
        zones[zone_id] = {"start": start["position"] if start else None, "end": end["position"] if end else None,
                          "track_path": path_id, "start_geometry": start, "end_geometry": end,
                          "calibrated": bool(data.get("calibrated", False))}
    receivers = []
    design_receivers = design.get("receivers", {})
    for receiver in ir.get("receivers", []):
        source = design_receivers.get(receiver["id"], {})
        association = (marker_geometry.get("markers", {}) or {}).get(receiver["id"], {})
        projection = _project(geometry, "JMRI" if imported else association.get("track_path", "Main"), source.get("position"), {} if imported else association) if source.get("position") else None
        receivers.append({"id": receiver["id"], "name": receiver.get("description", receiver["id"]),
                          "channel": receiver.get("channel"), "zones": receiver.get("zones", []),
                          "position": projection["position"] if projection else None,
                          "geometry": projection,
                          "calibrated": bool(source.get("verified", False))})
    turnouts = {}
    design_turnouts = design.get("turnouts", {})
    for turnout_id, data in (track.get("powered_turnouts", {}) or {}).items():
        source = design_turnouts.get(turnout_id, {})
        association = (marker_geometry.get("markers", {}) or {}).get(turnout_id, {})
        projection = _project(geometry, "JMRI" if imported else association.get("track_path", "Main"), source.get("position"), {} if imported else association) if source.get("position") else None
        turnouts[turnout_id] = {**data, "position": projection["position"] if projection else None,
                                "geometry": projection,
                                "calibrated": bool(source.get("verified", False))}
    validation = validate_graph(geometry)
    return {"coordinate_system": "clean_image_normalized_0_to_1",
            "image": {"path": "/dashboard/images/railroad-layout-clean.png", "width": int(CLEAN_WIDTH), "height": int(CLEAN_HEIGHT),
                      "source_image": design.get("source_image", "railroad-map-exact.png"),
                      "source_width": int(DESIGN_WIDTH), "source_height": int(DESIGN_HEIGHT),
                      "crop_offset": [0, 0],
                      "coordinate_transform": "scale only; source is already cropped"},
            "design_verified": bool((design.get("meta") or {}).get("verified", design.get("verified", False))),
            "geometry_verified": bool(geometry.get("verified", False)), "geometry_source": geometry.get("source_file", "hand-traced"),
            "graph_valid": validation["ok"], "graph_errors": validation["errors"],
            "centerlines": geometry.get("segments", {}), "segments": geometry.get("segments", {}),
            "junctions": geometry.get("junctions", {}), "terminals": geometry.get("terminals", []), "connections": geometry.get("connections", []),
            "turnout_graph": geometry.get("turnouts", {}), "turnout_reconciliation": reconciliation, "yard_tracks": geometry.get("yard_tracks", {}),
            "zones": zones, "ir_receivers": receivers, "turnouts": turnouts}
