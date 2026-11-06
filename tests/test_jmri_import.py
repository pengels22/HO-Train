from pathlib import Path
from railroad.jmri_import import import_jmri

SOURCE = Path("/Users/patrickengels/Downloads/dream train lauyout.xml")

def test_jmri_import_preserves_exported_counts_and_ids():
    data = import_jmri(SOURCE)
    assert data["counts"] == {"positionable_points": 86, "segments": 99, "arcs": 49, "beziers": 4, "straight": 46, "turnouts": 11}
    assert set(data["segments"]) == {f"T{i}" for i in range(99)}
    assert data["zero_length_segments"] == ["T80", "T81", "T82", "T83", "T84"]
    assert data["turntable"]["id"] == "TUR0"

def test_jmri_import_preserves_connections_and_marks_transform_unverified():
    data = import_jmri(SOURCE)
    assert data["verified"] is False
    assert data["transform"]["offset_x"] > 0
    assert data["transform"]["offset_y"] < 0
    assert "rail-extents" in data["transform"]["method"]
    assert data["segments"]["T56"]["source_kind"] == "bezier"
    assert data["segments"]["T6"]["source_kind"] == "arc"
    assert data["segments"]["T6"]["start"] == "A10"
    assert data["segments"]["T6"]["end"] == "A11"
