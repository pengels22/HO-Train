import pytest
from railroad.joystick.attack3 import JoystickMapping
from railroad.locomotives.manager import LocomotiveManager
from railroad.tracking.ir_protocol import Target, decode, encode
from railroad.tracking.occupancy import OccupancyState, Section
from railroad.routing.track_graph import TrackGraph
from railroad.automation.tipper import Tipper, TipperState

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
