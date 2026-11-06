"""Explicit native-pixel rail graph and marker projection helpers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import yaml


@dataclass(frozen=True)
class Projection:
    path_id: str
    segment_id: str
    distance_px: float
    point: tuple[float, float]
    error_px: float


def load_centerlines(root: Path) -> dict:
    return yaml.safe_load((root / "config/track_centerlines.yaml").read_text()) or {}


def _segment_items(geometry: dict):
    return geometry.get("segments", {})

def _segments(segment_id: str, segment: dict):
    points = [(float(x), float(y)) for x, y in segment.get("points", [])]
    distance = 0.0
    for index, (a, b) in enumerate(zip(points, points[1:])):
        length = math.dist(a, b)
        yield index, a, b, distance, length
        distance += length

def _candidate_segments(geometry, path_id=None, segment_id=None):
    if segment_id:
        if segment_id not in _segment_items(geometry):
            raise KeyError(segment_id)
        return [(segment_id, _segment_items(geometry)[segment_id])]
    return [(sid, seg) for sid, seg in _segment_items(geometry).items()
            if path_id is None or seg.get("track_path", seg.get("path_id")) == path_id]


def project_point(geometry: dict, path_id: str, point, segment_id=None) -> Projection:
    candidates = _candidate_segments(geometry, path_id, segment_id)
    px, py = map(float, point)
    best = None
    for sid, seg in candidates:
        for index, (ax, ay), (bx, by), distance, length in _segments(sid, seg):
            if not length: continue
            ux, uy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px-ax)*ux + (py-ay)*uy)/(length*length)))
            q = (ax+t*ux, ay+t*uy)
            error = math.dist((px, py), q)
            candidate = Projection(seg.get("track_path", path_id), sid, distance+t*length, q, error)
            if best is None or candidate.error_px < best.error_px: best = candidate
    if best is None:
        raise ValueError(f"no usable segment for {path_id or segment_id}")
    return best


def point_at_distance(geometry: dict, segment_id: str, distance_px: float):
    path = _segment_items(geometry)[segment_id]
    target = max(0.0, float(distance_px))
    last = None
    for _, a, b, start, length in _segments(segment_id, path):
        last = b
        if target <= start + length:
            t = 0.0 if not length else (target - start) / length
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return last or tuple(path["points"][0])


def normalized_projection(projection: Projection, width: float = 752, height: float = 602) -> dict:
    return {"track_path": projection.path_id, "segment_id": projection.segment_id,
            "distance_px": round(projection.distance_px, 3),
            "position": [projection.point[0] / width, projection.point[1] / height],
            "alignment_error_px": round(projection.error_px, 3)}

def validate_graph(geometry: dict) -> dict:
    errors = []
    segments = _segment_items(geometry)
    junctions = geometry.get("junctions", {})
    terminals = set(geometry.get("terminals", []))
    for sid, seg in segments.items():
        if len(seg.get("points", [])) < 2: errors.append(f"{sid}: fewer than two control points")
        for key in ("start", "end"):
            endpoint = seg.get(key)
            if not endpoint: errors.append(f"{sid}: missing {key} endpoint")
            elif endpoint not in junctions and endpoint not in terminals:
                errors.append(f"{sid}: unsupported {key} endpoint {endpoint}")
    for connection in geometry.get("connections", []):
        for key in ("from", "to"):
            ref = connection.get(key, "")
            if ":" not in ref or ref.split(":", 1)[0] not in segments:
                errors.append(f"unsupported connection {ref}")
    return {"ok": not errors, "errors": errors}
