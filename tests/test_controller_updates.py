import pytest
from railroad.dispatcher import Dispatcher, Cargo, SafetyError
from railroad.transport.udp import Command
from railroad.yard import YardPower

def test_zone_exclusivity():
    d = Dispatcher()
    d.reserve(1, ["MAIN-2"], "Mine")
    with pytest.raises(SafetyError):
        d.reserve(2, ["MAIN-2"])
    with pytest.raises(SafetyError):
        d.reserve(2, ["FARM-1"], "Mine")
    d.enter(1, "MAIN-2")
    with pytest.raises(SafetyError):
        d.tail_clear(1, "MAIN-2", last_car_confirmed=False)
    d.hall_clear(1, "MAIN-2", detected_cars=3, expected_cars=3)
    assert d.zones["MAIN-2"] is None

def test_tipper_and_freight():
    d = Dispatcher()
    d.set_tipper("ROTATING")
    assert not d.route_available(1, ["MAIN-3"])
    assert d.route_available(1, ["MAIN-2", "MINE-1"])
    d.set_tipper("IDLE")
    d.assign_destination(1, "Farm")
    d.complete_loading(1, "Farm")
    assert d.trains[1].cargo == Cargo.CORN
    with pytest.raises(SafetyError):
        d.assign_destination(1, "Mine")
    d.assign_destination(1, "Tipper")
    d.complete_tipping(1, success=True, safe_to_depart=True)
    d.assign_destination(1, "Mine")

def test_missed_checkpoint_global_stop():
    d = Dispatcher()
    d.trains[1].expected_checkpoint = "Ski Entrance"
    d.trains[1].checkpoint_deadline = 10
    d.trains[2].velocity = 100
    d.check_deadlines(now=11)
    assert d.global_stop and d.trains[2].velocity == 0

def test_shared_yard_and_udp_frame():
    y = YardPower()
    y.park("1A", 1)
    y.park("1B", 2)
    with pytest.raises(RuntimeError):
        y.energize_for_departure("1A", set(), True)
    y.energize_for_departure("1A", {2}, True)
    assert y.enabled["1"] and not y.enabled["2"]
    pkt = Command(2, 5, -120, 5).encode()
    assert Command.decode(pkt).speed == -120
