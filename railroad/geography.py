"""Authoritative geography loaded from ``config/unified_geography.json``.

The unified file is treated as data, not as a tracing hint.  No crop offset,
nearest-track projection, or geometry regeneration is performed here.
"""
from __future__ import annotations

import json
from pathlib import Path
import yaml
from railroad.track_geometry import validate_graph

DESIGN_WIDTH, DESIGN_HEIGHT = 739.0, 593.0
CLEAN_WIDTH, CLEAN_HEIGHT = DESIGN_WIDTH, DESIGN_HEIGHT


def source_pixel_to_clean_normalized(point):
    x, y = map(float, point)
    return [x / DESIGN_WIDTH, y / DESIGN_HEIGHT]


def clean_normalized_to_source_pixel(point):
    x, y = map(float, point)
    return [x * DESIGN_WIDTH, y * DESIGN_HEIGHT]


def _point(x, y):
    if x is None or y is None:
        return None
    return [float(x), float(y)]


def _geometry_position(point, verified=False):
    if point is None:
        return None
    return {"position": source_pixel_to_clean_normalized(point), "track_path": None,
            "segment_id": None, "distance_px": None, "alignment_error_px": None,
            "verified": bool(verified), "source": "config/unified_geography.json"}


def _load_unified(root: Path) -> dict:
    data = json.loads((root / "config/unified_geography.json").read_text())
    meta = data.get("meta", {})
    segments, junctions, connections = {}, {}, []
    for raw in data.get("trackGeometry", []):
        sid = raw["id"]
        endpoints = list(raw.get("sourceEndpoints", []))
        segment = {"id": sid, "name": raw.get("name", sid), "track_path": raw.get("line"),
                   "source_id": sid, "source_kind": raw.get("segmentKind"), "source": raw.get("source"),
                   "points": [[float(p["x"]), float(p["y"])] for p in raw.get("points", [])],
                   "start": endpoints[0] if endpoints else None, "end": endpoints[-1] if endpoints else None,
                   "status": raw.get("status"), "verified": bool(raw.get("verified", False))}
        segments[sid] = segment
        for endpoint in endpoints:
            junctions.setdefault(endpoint, {"type": "named_endpoint", "source": "JMRI"})
        if len(endpoints) >= 2:
            connections.append({"segment_id": sid, "from": endpoints[0], "to": endpoints[-1], "source": "unified_geography"})
    graph = {"coordinate_system": "original-mockup-739x593", "width": 739, "height": 593,
             "verified": False, "segments": segments, "junctions": junctions, "terminals": [],
             "connections": connections, "turnouts": {t["id"]: t for t in data.get("turnouts", [])},
             "yard_tracks": {"1": ["1A", "1B"], "2": ["2"], "3": ["3"]}}
    validation = validate_graph(graph)
    graph_valid = bool(meta.get("geometry_topology_verified", False) and validation["ok"])

    zones = {}
    for raw in data.get("zones", []):
        bounds = raw.get("boundaries", {})
        start = _point(bounds.get("start", {}).get("x"), bounds.get("start", {}).get("y"))
        end = _point(bounds.get("end", {}).get("x"), bounds.get("end", {}).get("y"))
        zones[raw["id"]] = {"start": source_pixel_to_clean_normalized(start) if start else None,
                            "end": source_pixel_to_clean_normalized(end) if end else None,
                            "track_path": raw.get("line"),
                            "start_geometry": _geometry_position(start, raw.get("verified", False)),
                            "end_geometry": _geometry_position(end, raw.get("verified", False)),
                            "calibrated": False, "verified": bool(raw.get("verified", False))}

    ir_config = yaml.safe_load((root / "config/ir_receivers.yaml").read_text()) or {}
    configured_ir = ir_config.get("receivers", [])
    receivers = []
    for index, raw in enumerate(data.get("receivers", [])):
        cfg = configured_ir[index] if index < len(configured_ir) else {}
        point = _point(raw.get("x"), raw.get("y"))
        receiver_id = cfg.get("id", f"ir_{index + 1:02d}")
        receivers.append({"id": receiver_id, "name": raw.get("displayName", raw.get("name", receiver_id)),
                          "channel": cfg.get("channel"), "zones": cfg.get("zones", []),
                          "position": source_pixel_to_clean_normalized(point) if point else None,
                          "geometry": _geometry_position(point, raw.get("verified", False)),
                          "calibrated": False, "verified": bool(raw.get("verified", False))})

    turnouts = {}
    for raw in data.get("turnouts", []):
        point = _point(raw.get("x"), raw.get("y"))
        turnouts[raw["id"]] = {**raw, "default": raw.get("defaultPosition", "straight"),
                                "position": source_pixel_to_clean_normalized(point) if point else None,
                                "geometry": _geometry_position(point, raw.get("verified", False)), "calibrated": False}

    halls = []
    for raw in data.get("trackSensors", []):
        point = _point(raw.get("x"), raw.get("y"))
        halls.append({**raw, "position": source_pixel_to_clean_normalized(point) if point else None,
                      "geometry": _geometry_position(point, raw.get("verified", False)),
                      "verified": bool(raw.get("verified", False))})

    return {"coordinate_system": "original-mockup-739x593",
            "image": {"path": "/dashboard/images/railroad-layout-clean.png", "width": 752, "height": 602,
                      "source_image": meta.get("image", "original-mockup-map.png"), "source_width": 739,
                      "source_height": 593, "crop_offset": [0, 0], "coordinate_transform": "native unified pixels; no crop offset"},
            "design_verified": bool(meta.get("verified", False)), "geometry_verified": False,
            "geometry_visual_alignment_verified": bool(meta.get("geometry_visual_alignment_verified", False)),
            "geometry_topology_verified": bool(meta.get("geometry_topology_verified", False)),
            "geometry_source": "config/unified_geography.json", "graph_valid": graph_valid,
            "graph_errors": validation["errors"] if not validation["ok"] else ([] if graph_valid else ["unified geometry topology is not verified"]),
            "centerlines": segments, "segments": segments, "junctions": junctions, "terminals": [],
            "connections": connections, "turnout_graph": graph["turnouts"],
            "turnout_reconciliation": {"powered": [t["id"] for t in data.get("turnouts", [])], "passive": ["P1", "P2", "P3"]},
            "yard_tracks": graph["yard_tracks"], "zones": zones, "ir_receivers": receivers,
            "turnouts": turnouts, "hall_sensors": halls, "hall_sensor_count": len(halls),
            "track_geometry_count": len(segments), "meta": meta}


def load_geography(root: Path) -> dict:
    if (root / "config/unified_geography.json").exists():
        return _load_unified(root)
    from railroad.track_geometry import load_centerlines
    geometry = load_centerlines(root)
    return {"coordinate_system": "clean_image_normalized_0_to_1",
            "image": {"path": "/dashboard/images/railroad-layout-clean.png", "width": 752, "height": 602},
            "geometry_verified": bool(geometry.get("verified", False)), "graph_valid": False,
            "graph_errors": ["unified geography is unavailable"], "centerlines": geometry.get("segments", {}),
            "segments": geometry.get("segments", {}), "junctions": geometry.get("junctions", {}),
            "terminals": geometry.get("terminals", []), "connections": geometry.get("connections", []),
            "turnout_graph": geometry.get("turnouts", {}), "zones": {}, "ir_receivers": [], "turnouts": {}, "hall_sensors": []}
