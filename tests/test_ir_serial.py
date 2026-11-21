import pytest

from railroad.tracking.ir_serial import parse_event
from railroad.transport.ir_bench import BenchIRReader


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


def test_bench_reader_resolves_physical_channel_from_config():
    reader = BenchIRReader("/dev/null", 115200, lambda event: None,
                           receiver_map={("channel", "1"): "mine_station", ("pin", "D2"): "mine_station"})
    payload = reader._resolve_configured_receiver({"channel": 1, "pin": "D2", "train_id": 2})
    assert payload["station_id"] == "mine_station"
    assert "receiver" not in payload


def test_bench_reader_delivers_real_event_and_suppresses_no_train():
    events = []
    reader = BenchIRReader("/dev/null", 115200, events.append,
                           receiver_map={("channel", "1"): "mine_station"})
    reader._handle_line(b'{"channel":1,"train_id":2,"timestamp_ms":123}\n')
    reader._handle_line(b'{"channel":1,"train_id":"no_train"}\n')
    assert len(events) == 1
    assert events[0].receiver_id == "Mine Station"
    assert events[0].train_id == 2
    assert reader.last_event["train_id"] == "no_train"
