from pathlib import Path
import yaml

from railroad.track_geometry import load_centerlines, point_at_distance, project_point


def test_projection_to_curve_segment_and_distance_persistence():
    geometry = {"paths": {"curve": {"points": [[0, 0], [10, 10], [20, 0]]}}}
    projection = project_point(geometry, "curve", [10, 8])
    assert projection.segment_id == "curve:0"
    assert projection.point == (9.0, 9.0)
    assert point_at_distance(geometry, "curve", projection.distance_px) == projection.point


def test_crossing_selection_is_explicit_path_not_global_nearest():
    geometry = {"paths": {
        "north": {"points": [[0, 10], [20, 10]]},
        "south": {"points": [[0, 12], [20, 12]]},
    }}
    assert project_point(geometry, "south", [10, 10.1]).path_id == "south"


def test_production_centerlines_are_native_image_space_and_unverified():
    geometry = load_centerlines(Path(__file__).parents[1])
    assert geometry["coordinate_system"] == "clean_image_pixels"
    assert (geometry["width"], geometry["height"]) == (752, 602)
    assert geometry["verified"] is False
    assert set(geometry["paths"]) == {"Ski", "Farm", "Underground", "Mine", "Main"}


def test_marker_geometry_persists_explicit_track_associations():
    root = Path(__file__).parents[1]
    data = yaml.safe_load((root / "config/marker_geometry_v05.yaml").read_text())
    assert data["markers"]["tunnel_entrance"]["track_path"] == "Ski"
    assert data["markers"]["A"]["track_path"] == "Main"
