import pytest
from railroad.dispatcher import Dispatcher,Cargo,SafetyError
from railroad.transport.udp import Command
from railroad.tracking.ir_serial import parse_event
from railroad.yard import YardPower

def test_exclusive_zone_and_destination():
    d=Dispatcher()
    d.reserve(1,["MAIN-2"],"Mine")
    with pytest.raises(SafetyError):d.reserve(2,["MAIN-2"])
    with pytest.raises(SafetyError):d.reserve(2,["FARM-1"],"Mine")
    d.enter(1,"MAIN-2")
    with pytest.raises(SafetyError):d.tail_clear(1,"MAIN-2",last_car_confirmed=False)
    d.hall_clear(1,"MAIN-2",detected_cars=3,expected_cars=3)
    assert d.zones["MAIN-2"] is None

def test_tipper_lockout_and_mine_exception():
    d=Dispatcher()
    d.set_tipper("ROTATING")
    assert not d.route_available(1,["MAIN-3"])
    assert not d.route_available(1,["UND-1"])
    assert d.route_available(1,["MAIN-2","MINE-1"])
    d.set_tipper("IDLE")

def test_material_change_only_after_tipping():
    d=Dispatcher()
    d.assign_destination(1,"Farm")
    d.complete_loading(1,"Farm")
    with pytest.raises(SafetyError):d.assign_destination(1,"Mine")
    d.assign_destination(1,"Tipper")
    d.complete_tipping(1,success=True,safe_to_depart=True)
    d.assign_destination(1,"Mine")

def test_tipper_failure_recovery():
    d=Dispatcher()
    d.assign_destination(1,"Farm");d.complete_loading(1,"Farm")
    d.assign_destination(1,"Tipper")
    d.set_tipper("FAULT","alignment")
    assert d.trains[1].destination=="Yard"
    assert d.trains[1].cargo==Cargo.UNKNOWN
    assert d.global_stop
    with pytest.raises(SafetyError):d.clear_tipper_fault(True,False,True)
    d.clear_tipper_fault(True,True,True)
    assert d.global_stop

def test_cycle_mandatory_unload():
    d=Dispatcher()
    with pytest.raises(SafetyError):d.set_cycle(1,["Farm","Mine","Tipper"])
    d.set_cycle(1,["Farm","Tipper","Mine","Tipper","Yard"])
    with pytest.raises(SafetyError):d.set_cycle(4,["Ski","Tipper"])

def test_missed_checkpoint_stops_all():
    d=Dispatcher()
    d.trains[1].expected_checkpoint="Ski Entrance"
    d.trains[1].checkpoint_deadline=10
    d.trains[2].velocity=70
    d.check_deadlines(now=11)
    assert d.global_stop and d.trains[2].velocity==0

def test_yard_shared_power():
    y=YardPower();y.park("1A",1);y.park("1B",2)
    with pytest.raises(RuntimeError):y.energize_for_departure("1A",set(),True)
    y.energize_for_departure("1A",{2},True)
    assert y.enabled["1"] and not y.enabled["2"]

def test_udp_crc_and_serial():
    msg=Command(3,17,-120,5).encode()
    assert Command.decode(msg).speed==-120
    with pytest.raises(ValueError):Command.decode(msg[:-1]+b"\x00")
    assert parse_event('{"receiver":"Stall 1A","train_id":2}')["train_id"]==2
