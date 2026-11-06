from pathlib import Path
import yaml
import pytest

from railroad.track_geometry import load_centerlines, point_at_distance, project_point


def test_projection_to_curve_segment_and_distance_persistence():
    geometry = {"segments": {"curve": {"track_path": "Farm", "start": "a", "end": "b", "points": [[0, 0], [10, 10], [20, 0]]}}, "junctions": {"a": {}, "b": {}}}
    projection = project_point(geometry, "Farm", [10, 8])
    assert projection.segment_id == "curve"
    assert projection.point == (9.0, 9.0)
    assert point_at_distance(geometry, "curve", projection.distance_px) == projection.point


def test_crossing_selection_is_explicit_path_not_global_nearest():
    geometry = {"segments": {
        "north": {"track_path": "north", "start": "n0", "end": "n1", "points": [[0, 10], [20, 10]]},
        "south": {"track_path": "south", "start": "s0", "end": "s1", "points": [[0, 12], [20, 12]]},
    }, "junctions": {"n0": {}, "n1": {}, "s0": {}, "s1": {}}}
    assert project_point(geometry, "south", [10, 10.1]).path_id == "south"


def test_production_centerlines_are_native_image_space_and_unverified():
    geometry = load_centerlines(Path(__file__).parents[1])
    assert geometry["coordinate_system"] == "clean_image_pixels"
    assert (geometry["width"], geometry["height"]) == (752, 602)
    assert geometry["verified"] is False
    assert len(geometry["segments"]) >= 15
    assert len(geometry["turnouts"]) == 11

def test_graph_has_no_proximity_connections_and_validates_explicit_endpoints():
    geometry = load_centerlines(Path(__file__).parents[1])
    from railroad.track_geometry import validate_graph
    result = validate_graph(geometry)
    assert result["ok"], result["errors"]
    assert all(c.get("segment_id") in geometry["segments"] for c in geometry["connections"])

def test_marker_projection_can_be_persisted_to_a_specific_segment():
    geometry = {"segments": {"farm_outer": {"track_path": "Farm", "start": "a", "end": "b", "points": [[0, 0], [10, 0], [20, 10]]}}, "junctions": {"a": {}, "b": {}}}
    projection = project_point(geometry, "Farm", [10, 1], "farm_outer")
    assert projection.segment_id == "farm_outer"
    assert point_at_distance(geometry, projection.segment_id, projection.distance_px) == pytest.approx(projection.point)


def test_marker_geometry_persists_explicit_track_associations():
    root = Path(__file__).parents[1]
    data = yaml.safe_load((root / "config/marker_geometry_v05.yaml").read_text())
    assert data["markers"]["tunnel_entrance"]["track_path"] == "Ski"
    assert data["markers"]["A"]["track_path"] == "Main"

def test_split_segment_is_explicit_and_does_not_join_nearby_tracks():
    from railroad.track_geometry import split_segment, validate_graph
    geometry = {"segments": {"rail": {"track_path": "Main", "start": "a", "end": "b", "points": [[0, 0], [5, 0], [10, 0]]}}, "junctions": {"a": {}, "b": {}}, "connections": []}
    edited = split_segment(geometry, "rail", 1)
    assert set(edited["segments"]) == {"rail_a", "rail_b"}
    assert edited["segments"]["rail_a"]["end"] == edited["segments"]["rail_b"]["start"]
    assert validate_graph(edited)["ok"]
    assert geometry["segments"]["rail"]["points"] == [[0, 0], [5, 0], [10, 0]]

def test_invalid_endpoint_connection_is_reported_for_editor_validation():
    from railroad.track_geometry import validate_graph
    geometry = {"segments": {"rail": {"track_path": "Main", "start": "missing", "end": "b", "points": [[0, 0], [1, 0]]}}, "junctions": {"b": {}}}
    result = validate_graph(geometry)
    assert not result["ok"]
    assert any("unsupported start endpoint" in error for error in result["errors"])
