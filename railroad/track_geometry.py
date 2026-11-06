"""Native-image track centerlines and marker projection helpers."""
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


def _segments(path: dict):
    points = [(float(x), float(y)) for x, y in path.get("points", [])]
    distance = 0.0
    for index, (a, b) in enumerate(zip(points, points[1:])):
        length = math.dist(a, b)
        yield index, a, b, distance, length
        distance += length


def project_point(geometry: dict, path_id: str, point: tuple[float, float] | list[float]) -> Projection:
    path = geometry["paths"][path_id]
    px, py = map(float, point)
    best = None
    for index, (ax, ay), (bx, by), distance, length in _segments(path):
        if not length:
            continue
        ux, uy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((px - ax) * ux + (py - ay) * uy) / (length * length)))
        q = (ax + t * ux, ay + t * uy)
        error = math.dist((px, py), q)
        candidate = (error, Projection(path_id, f"{path_id}:{index}", distance + t * length, q, error))
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        raise ValueError(f"path {path_id} has fewer than two usable points")
    return best[1]


def point_at_distance(geometry: dict, path_id: str, distance_px: float) -> tuple[float, float]:
    path = geometry["paths"][path_id]
    target = max(0.0, float(distance_px))
    last = None
    for _, a, b, start, length in _segments(path):
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
