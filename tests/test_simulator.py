import pytest

from railroad.dispatcher import Dispatcher, SafetyError
from railroad.simulator.engine import Car, Consist, SimulationEngine


def path(*, checkpoints=(), halls=()):
    return {"verified": True, "paths": {"main": {
        "length_mm": 1000,
        "points": [[0.1, 0.5], [0.5, 0.5], [0.9, 0.5]],
        "checkpoints": list(checkpoints),
        "hall_sensors": list(halls),
    }}}


def running_engine(data):
    dispatcher = Dispatcher()
    engine = SimulationEngine(dispatcher, data, clock=lambda: 0.0)
    engine.dispatch(1, "main", target_speed_mm_s=100)
    engine.start()
    return dispatcher, engine


def test_engine_refuses_unverified_geometry():
    engine = SimulationEngine(Dispatcher(), {"verified": False, "paths": {}})
    with pytest.raises(SafetyError):
        engine.start()


def test_engine_moves_on_calibrated_centerline_and_logs_ir():
    dispatcher, engine = running_engine(path(checkpoints=[{"id": "cp-1", "distance_mm": 50, "zone": "MAIN-1"}]))
    dispatcher.trains[1].expected_checkpoint = "cp-1"
    dispatcher.trains[1].checkpoint_deadline = 2
    engine.advance(2)
    assert engine.trains[1].last_position is not None
    assert dispatcher.trains[1].last_checkpoint == "cp-1"
    assert any(e["event"] == "ir_event" for e in engine.events)


def test_all_four_locomotives_can_advance_together():
    dispatcher = Dispatcher()
    engine = SimulationEngine(dispatcher, {"verified": True, "paths": {
        f"path-{i}": {"length_mm": 500, "points": [[0.1, i / 10], [0.9, i / 10]], "checkpoints": [], "hall_sensors": []}
        for i in range(1, 5)
    }}, clock=lambda: 0.0)
    for i in range(1, 5):
        engine.dispatch(i, f"path-{i}", target_speed_mm_s=50)
    engine.start(); engine.advance(2)
    assert all(engine.trains[i].distance_mm > 0 for i in range(1, 5))


def test_consist_only_clears_after_final_magnetic_strip():
    dispatcher, engine = running_engine(path(halls=[
        {"id": "hall-1", "distance_mm": 100, "zone": "MAIN-1", "last_car": False},
        {"id": "hall-2", "distance_mm": 200, "zone": "MAIN-1", "last_car": True},
    ]))
    dispatcher.reserve(1, ["MAIN-1"])
    dispatcher.enter(1, "MAIN-1")
    engine.trains[1].consist = Consist((Car(), Car()))
    engine.advance(3)
    assert dispatcher.zones["MAIN-1"] is None
    assert any(e["event"] == "train_clear" for e in engine.events)


def test_missed_ir_latches_global_stop():
    dispatcher, engine = running_engine(path(checkpoints=[{"id": "cp-1", "distance_mm": 50}]))
    engine.inject_fault("missed_ir", 1)
    engine.advance(3)
    assert dispatcher.global_stop
    assert "missed" in dispatcher.stop_reason


@pytest.mark.parametrize("fault", ["failed_turnout", "stall", "tipper"])
def test_faults_are_deterministic(fault):
    dispatcher, engine = running_engine(path())
    engine.inject_fault(fault, 1 if fault == "stall" else None)
    if fault == "stall":
        engine.advance(2)
        assert engine.trains[1].distance_mm == 0
    else:
        assert dispatcher.global_stop


def test_stuck_hall_does_not_clear_zone():
    dispatcher, engine = running_engine(path(halls=[{"id": "hall", "distance_mm": 100, "zone": "MAIN-1", "last_car": True}]))
    dispatcher.reserve(1, ["MAIN-1"])
    dispatcher.enter(1, "MAIN-1")
    engine.inject_fault("stuck_hall", 1)
    engine.advance(2)
    assert dispatcher.zones["MAIN-1"] == 1


def test_loading_tipper_and_shared_yard_power_use_dispatcher_state():
    dispatcher, engine = running_engine(path())
    dispatcher.assign_destination(1, "Mine")
    engine.load(1, "Mine")
    assert dispatcher.trains[1].cargo.value == "ORE"
    dispatcher.assign_destination(1, "Tipper")
    engine.unload_tipper(1)
    assert dispatcher.trains[1].cargo.value == "EMPTY"
    engine.set_yard_power("1", True)
    assert dispatcher.yard_power["1"] is True
    engine.park(1, "1A")
    assert dispatcher.yard_power["1"] is False
    assert dispatcher.trains[1].parked == "1A"
