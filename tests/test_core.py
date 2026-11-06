import pytest
from railroad.joystick.attack3 import JoystickMapping
from railroad.locomotives.manager import LocomotiveManager
from railroad.tracking.ir_protocol import Target, decode, encode
from railroad.tracking.occupancy import OccupancyState, Section
from railroad.routing.track_graph import TrackGraph
from railroad.automation.tipper import Tipper, TipperState
from railroad.config.zones import load_zones
from railroad.routing.zones import ZoneState

def test_joystick_dead_zone_and_scale():
    m = JoystickMapping()
    assert m.normalize_axis(20) == 0
    assert m.normalize_axis(-20) == 0
    assert m.normalize_axis(32767) == 255
    assert m.normalize_axis(-32768) == -255

def test_selection_and_manual_target_are_independent():
    mgr = LocomotiveManager()
    mgr.select(2); mgr.joystick_speed(55)
    assert mgr.trains[2].throttle.target == "MANUAL"
    assert mgr.trains[1].throttle.speed == 0

def test_ir_signed_speed_and_crc():
    packet = encode(2, 1, Target.YARD, -120)
    assert decode(packet)["speed"] == -120
    broken = packet[:-1] + bytes([packet[-1] ^ 1])
    with pytest.raises(ValueError): decode(broken)

def test_route_conflict():
    graph = TrackGraph()
    graph.add_section(Section("shared", state=OccupancyState.CLEAR))
    graph.reserve(["shared"], 1)
    assert not graph.route_available(["shared"], 2)

def test_tipper_interlock_and_fault():
    tipper = Tipper()
    with pytest.raises(RuntimeError): tipper.start(True, False)
    tipper.start(True, True); tipper.rotate(1)
    assert tipper.state == TipperState.ROTATING
    tipper.fail("timeout")
    assert tipper.state == TipperState.FAULT

def test_fifteen_zone_configuration_is_conservative():
    engine = load_zones("config/zones.yaml")
    assert len(engine.zones) == 15
    assert {z.railway for z in engine.zones.values()} == {"Ski Line", "Farm Line", "Underground", "Mine Line", "Main Line"}
    with pytest.raises(RuntimeError):
        engine.reserve_route(["MAIN-1"], 1)

def test_zone_ir_does_not_clear_previous_consist_zone():
    engine = load_zones("config/zones.yaml")
    previous = engine.zones["MAIN-1"]
    previous.verified = True
    previous.state = ZoneState.CLEAR
    previous.reserve(1, require_verified=True)
    previous.observe_ir(1, "tunnel_entrance")
    next_zone = engine.zones["MAIN-2"]
    next_zone.verified = True
    next_zone.state = ZoneState.CLEAR
    next_zone.reserve(1, require_verified=True)
    assert previous.state == ZoneState.OCCUPIED
    assert previous.occupying_train == 1

def test_zone_conflict_blocks_second_train():
    engine = load_zones("config/zones.yaml")
    zone = engine.zones["MAIN-1"]
    zone.verified = True
    zone.state = ZoneState.CLEAR
    engine.reserve_route(["MAIN-1"], 1)
    assert engine.conflict(["MAIN-1"], 2)
