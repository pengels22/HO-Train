from pathlib import Path
import struct

from railroad.geography import clean_normalized_to_source_pixel, load_geography, source_pixel_to_clean_normalized


def test_clean_image_transform_is_single_crop_transform():
    assert source_pixel_to_clean_normalized([0, 0]) == [0.0, 0.0]
    assert source_pixel_to_clean_normalized([739, 593]) == [1.0, 1.0]
    assert clean_normalized_to_source_pixel([0.5, 0.5]) == [369.5, 296.5]


def test_geography_has_fifteen_pairs_eleven_ir_and_seven_turnouts():
    geo = load_geography(Path(__file__).parents[1])
    assert len(geo["zones"]) == 15
    assert len(geo["ir_receivers"]) == 11
    assert len(geo["turnouts"]) == 7
    assert geo["zones"]["SKI-1"]["start_geometry"]["track_path"] == "Ski"
    assert geo["zones"]["SKI-1"]["start_geometry"]["segment_id"].startswith("Ski:")
    assert geo["ir_receivers"][0]["geometry"]["track_path"] == "Ski"
    assert geo["turnouts"]["A"]["geometry"]["track_path"] == "Main"
    assert all(v["start"] is not None and v["end"] is not None and not v["calibrated"] for v in geo["zones"].values())
    assert all(v["position"] is not None and not v["calibrated"] for v in geo["ir_receivers"])
    assert all(v["position"] is not None and v["calibrated"] for v in geo["turnouts"].values())
    assert geo["design_verified"] is False


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
