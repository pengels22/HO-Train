from railroad.dispatcher import Dispatcher
from railroad.transport.telemetry import ControllerHealthRegistry
from railroad.transport.usb import ControllerRegistry


def test_health_inventory_preserves_mixed_locomotive_controller_types():
    health = ControllerHealthRegistry(
        ControllerRegistry(), locomotive_ids=[1, 2],
        locomotive_types={1: "m5_atom_echo", 2: "xiao_esp32_c6"},
        independent_locomotives=True,
    )
    inventory = health.status()
    assert {item["type"] for item in inventory} == {"m5_atom_echo", "xiao_esp32_c6"}


def test_cycle_request_is_planned_but_never_acts_without_verified_hardware():
    dispatcher = Dispatcher()
    dispatcher.trains[1].control_mode = "automatic"
    dispatcher.trains[1].destination = "Mine"
    dispatcher.run_cycle_once()
    plan = dispatcher.snapshot()["last_cycle_plan"]
    assert plan["state"] == "PLANNED"
    assert plan["motion_issued"] is False


def test_yard_power_keeps_requested_and_verified_state_separate():
    dispatcher = Dispatcher()
    dispatcher.set_yard_power("1", True)
    snapshot = dispatcher.snapshot()
    assert snapshot["yard_power_requested"]["1"] is True
    assert snapshot["yard_power_verified"]["1"] is False
