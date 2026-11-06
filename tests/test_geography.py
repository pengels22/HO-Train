from pathlib import Path

from railroad.geography import clean_normalized_to_source_pixel, load_geography, source_pixel_to_clean_normalized


def test_clean_image_transform_is_single_crop_transform():
    assert source_pixel_to_clean_normalized([469, 205]) == [0.0, 0.0]
    assert source_pixel_to_clean_normalized([1221, 807]) == [1.0, 1.0]
    assert clean_normalized_to_source_pixel([0.5, 0.5]) == [845.0, 506.0]


def test_geography_has_fifteen_pairs_eleven_ir_and_seven_turnouts():
    geo = load_geography(Path(__file__).parents[1])
    assert len(geo["zones"]) == 15
    assert len(geo["ir_receivers"]) == 11
    assert len(geo["turnouts"]) == 7
    assert all(v["start"] is None and v["end"] is None for v in geo["zones"].values())
    assert all(v["position"] is None for v in geo["ir_receivers"])
    assert all(v["position"] is None for v in geo["turnouts"].values())
