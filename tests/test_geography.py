from pathlib import Path

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
    assert geo["zones"]["SKI-1"]["start"] == [0.744248985, 0.399662732]
    assert geo["zones"]["SKI-1"]["end"] == [0.913396482, 0.305227656]
    assert geo["ir_receivers"][0]["position"] == [0.387009472, 0.035413153]
    assert geo["turnouts"]["A"]["position"] == [0.104194858, 0.489038786]
    assert all(v["start"] is not None and v["end"] is not None and not v["calibrated"] for v in geo["zones"].values())
    assert all(v["position"] is not None and not v["calibrated"] for v in geo["ir_receivers"])
    assert all(v["position"] is not None and v["calibrated"] for v in geo["turnouts"].values())
    assert geo["design_verified"] is False
