from pathlib import Path
import struct

from railroad.geography import clean_normalized_to_source_pixel, load_geography, source_pixel_to_clean_normalized


def test_clean_image_transform_is_single_crop_transform():
    assert source_pixel_to_clean_normalized([0, 0]) == [0.0, 0.0]
    assert source_pixel_to_clean_normalized([739, 593]) == [1.0, 1.0]
    assert clean_normalized_to_source_pixel([0.5, 0.5]) == [369.5, 296.5]


def test_unified_geography_has_fifteen_pairs_eleven_ir_eight_turnouts_and_halls():
    geo = load_geography(Path(__file__).parents[1])
    assert len(geo["zones"]) == 15
    assert len(geo["ir_receivers"]) == 11
    assert len(geo["turnouts"]) == 8
    assert len(geo["hall_sensors"]) == 28
    assert geo["track_geometry_count"] == 89
    assert set(geo["turnouts"]) == set("ABCDEFGH")
    assert geo["zones"]["SKI-1"]["start_geometry"]["source"] == "config/unified_geography.json"
    assert geo["ir_receivers"][0]["geometry"]["source"] == "config/unified_geography.json"
    assert geo["turnouts"]["A"]["geometry"]["source"] == "config/unified_geography.json"
    assert all(v["start"] is not None and v["end"] is not None and not v["calibrated"] for v in geo["zones"].values())
    assert all(v["position"] is not None and not v["calibrated"] for v in geo["ir_receivers"])
    assert all(v["calibrated"] is False for v in geo["turnouts"].values())
    assert geo["turnouts"]["H"]["position"] is None
    assert geo["design_verified"] is False
    assert geo["geometry_verified"] is False
    assert geo["graph_valid"] is False


def test_clean_background_dimensions_and_mapping_are_stable():
    root = Path(__file__).parents[1]
    png = (root / "dashboard/public/images/railroad-layout-clean.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (752, 602)
    geo = load_geography(root)
    assert geo["image"]["crop_offset"] == [0, 0]
    assert geo["image"]["source_width"] == 739
    assert geo["image"]["source_height"] == 593
    assert source_pixel_to_clean_normalized([739, 593]) == [1.0, 1.0]
