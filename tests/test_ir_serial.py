import pytest

from railroad.tracking.ir_serial import parse_event


def test_parse_event_accepts_bench_station_endpoints():
    assert parse_event('{"receiver":"Mine Station","train_id":1,"speed":0}')["receiver"] == "Mine Station"


def test_parse_event_rejects_unknown_bench_endpoint():
    with pytest.raises(ValueError):
        parse_event('{"receiver":"Unknown Station","train_id":1,"speed":0}')
