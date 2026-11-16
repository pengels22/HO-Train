import pytest

from railroad.tracking.ir_serial import parse_event


def test_parse_event_accepts_bench_station_endpoints():
    assert parse_event('{"receiver":"Mine Station","train_id":1,"speed":0}')["receiver"] == "Mine Station"


def test_parse_event_rejects_unknown_bench_endpoint():
    with pytest.raises(ValueError):
        parse_event('{"receiver":"Unknown Station","train_id":1,"speed":0}')

def test_parse_event_accepts_nano_station_packet():
    event = parse_event('{"station_id":"mine_station","train_id":1}')
    assert event["receiver"] == "Mine Station"
    assert event["train_id"] == 1

def test_parse_event_accepts_explicit_no_train():
    event = parse_event('{"station_id":"mine_station","train_id":"no_train"}')
    assert event["receiver"] == "Mine Station"
    assert event["train_id"] == "no_train"
