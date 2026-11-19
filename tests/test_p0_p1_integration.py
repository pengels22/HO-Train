import pytest

from railroad.dispatcher import Dispatcher
from railroad.transport.telemetry import ControllerHealthRegistry
from railroad.transport.usb import ControllerRegistry
from railroad.api import server
from railroad.hardware.yard_power import YardOutput, YardPowerAdapter


def test_health_inventory_preserves_mixed_locomotive_controller_types():
    health = ControllerHealthRegistry(
        ControllerRegistry(), locomotive_ids=[1, 2],
        locomotive_types={1: "m5_atom_echo", 2: "xiao_esp32_c6"},
        independent_locomotives=True,
    )
    inventory = health.status()
    assert {item["type"] for item in inventory} == {"m5_atom_echo", "xiao_esp32_c6"}


def test_hardware_loader_accepts_mixed_declarative_fleet():
    config = {"locomotive_controllers": [
        {"id": 1, "type": "m5_atom_echo"},
        {"id": 2, "type": "xiao_esp32_c6"},
    ]}
    loaded = server.load_locomotive_controller_config(config, {1, 2, 3, 4})
    assert [row["type"] for row in loaded] == ["m5_atom_echo", "xiao_esp32_c6"]


def test_cycle_request_is_planned_but_never_acts_without_verified_hardware():
    dispatcher = Dispatcher()
    dispatcher.trains[1].control_mode = "automatic"
    dispatcher.trains[1].destination = "Mine"
    dispatcher.run_cycle_once()
    plan = dispatcher.snapshot()["last_cycle_plan"]
    assert plan["state"] == "READY"
    assert plan["motion_issued"] is False


def test_automatic_cycle_completes_from_real_checkpoint_events():
    dispatcher = Dispatcher()
    dispatcher.trains[1].destination = "Mine"
    commands = []
    dispatcher.attach_cycle_motion(lambda train_id, speed: commands.append((train_id, speed)))
    dispatcher.run_cycle_once()
    dispatcher.cycle_checkpoint("MAIN-2", zone="MAIN-2")
    dispatcher.cycle_checkpoint("MINE-1", zone="MINE-1", last_car_confirmed=True)
    assert dispatcher.snapshot()["cycle_state"] == "COMPLETED"
    assert commands == [(1, 64), (1, 0)]


def test_yard_power_keeps_requested_and_verified_state_separate():
    dispatcher = Dispatcher()
    dispatcher.set_yard_power("1", True)
    snapshot = dispatcher.snapshot()
    assert snapshot["yard_power_requested"]["1"] is True
    assert snapshot["yard_power_verified"]["1"] is False


def test_unassigned_yard_outputs_report_unassigned_and_refuse_activation():
    adapter = YardPowerAdapter.from_config({"yard_outputs": [
        {"track": 1, "sections": ["1A", "1B"], "gpio": None},
        {"track": 2, "sections": ["2"], "gpio": None},
        {"track": 3, "sections": ["3"], "gpio": None},
    ]})
    assert all(value == "UNASSIGNED" for value in adapter.status()["faults"].values())
    with pytest.raises(RuntimeError, match="unassigned"):
        adapter.set_power("1", True)
    adapter.set_power("1", False)
    assert adapter.status()["commanded"]["1"] is False


def test_yard_adapter_defaults_off_and_rejects_unassigned_activation():
    adapter = YardPowerAdapter([
        YardOutput("1", ("1A", "1B")), YardOutput("2", ("2",)), YardOutput("3", ("3",))
    ])
    assert all(not value for value in adapter.status()["commanded"].values())
    try:
        adapter.set_power("1", True)
    except RuntimeError as exc:
        assert "unassigned" in str(exc)
    else:
        raise AssertionError("unassigned yard output was activated")
