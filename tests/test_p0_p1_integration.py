import pytest

from railroad.dispatcher import Dispatcher
from railroad.transport.telemetry import ControllerHealthRegistry
from railroad.transport.usb import ControllerRegistry
from railroad.api import server
from railroad.hardware.yard_power import YardOutput, YardPowerAdapter
from railroad.routing.planner import RouteDefinition, RoutePlanner, RouteStatus


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


def test_route_planner_blocks_unverified_topology_without_hardware_success_claim():
    planner = RoutePlanner([RouteDefinition("Yard", "Mine", ("MAIN-2",), verified=False)])
    plan = planner.plan(1, "Yard", "Mine", zones={"MAIN-2": None}, reservations={"MAIN-2": None})
    assert plan.status is RouteStatus.BLOCKED
    assert "not physically verified" in plan.blocking_reason


def test_route_planner_requires_verified_feedback_and_isolates_missing_tipper():
    planner = RoutePlanner([RouteDefinition("Yard", "Tipper", ("MAIN-2",),
                                             (("D", "diverging"),),
                                             required_controllers=("tipper",), verified=True)])
    kwargs = {"zones": {"MAIN-2": None}, "reservations": {"MAIN-2": None},
              "controllers": {"tipper": False}, "turnouts": {"D": "diverging"}}
    offline = planner.plan(1, "Yard", "Tipper", **kwargs)
    assert offline.status is RouteStatus.OFFLINE
    assert "tipper" in offline.blocking_reason
    kwargs["controllers"]["tipper"] = True
    kwargs["turnouts"]["D"] = None
    blocked = planner.plan(1, "Yard", "Tipper", **kwargs)
    assert blocked.status is RouteStatus.BLOCKED
    assert "verified" in blocked.blocking_reason


def test_route_planner_derives_routes_from_declared_connections_and_blocks_only_bad_segment():
    planner = RoutePlanner.from_topology({
        "verified": False,
        "origins": ["Yard"],
        "destinations": ["Mine", "Farm"],
        "connections": [
            {"from": "Yard", "to": "MAIN-2", "zone": "MAIN-2", "verified": True},
            {"from": "MAIN-2", "to": "Mine", "zone": "MINE-1", "verified": True},
            {"from": "MAIN-2", "to": "Farm", "zone": "FARM-1", "verified": False,
             "segment": "MAIN-2/FARM-1"},
        ],
    })
    available = planner.plan(1, "Yard", "Mine", zones={"MAIN-2": None, "MINE-1": None},
                             reservations={"MAIN-2": None, "MINE-1": None})
    blocked = planner.plan(1, "Yard", "Farm", zones={"MAIN-2": None, "FARM-1": None},
                           reservations={"MAIN-2": None, "FARM-1": None})
    assert available.status is RouteStatus.AVAILABLE
    assert available.zones == ("MAIN-2", "MINE-1")
    assert blocked.status is RouteStatus.BLOCKED
    assert blocked.blocking_segment == "MAIN-2/FARM-1"


def test_request_queue_records_priority_and_skips_blocked_request():
    dispatcher = Dispatcher()
    dispatcher.trains[1].zone = "Yard"
    dispatcher.trains[2].zone = "Yard"
    dispatcher.route_planner = RoutePlanner.from_topology({
        "origins": ["Yard"], "destinations": ["Mine", "Farm"],
        "connections": [
            {"from": "Yard", "to": "Mine", "zone": "MAIN-1", "verified": False},
            {"from": "Yard", "to": "Farm", "zone": "MAIN-2", "verified": True},
        ],
    })
    first = dispatcher.submit_request(1, "Mine", priority=10)
    second = dispatcher.submit_request(2, "Farm", priority=1)
    assert first["priority"] == 10
    dispatcher.simulation = False
    dispatcher.run_cycle_once()
    states = {item["request_id"]: item["state"] for item in dispatcher.pending_requests}
    assert states[first["request_id"]] == "BLOCKED"
    assert states[second["request_id"]] == "BLOCKED" or dispatcher.active_request_id == second["request_id"]


def test_turnout_command_is_not_feedback_and_alignment_requires_confirmation():
    dispatcher = Dispatcher()
    plan = RoutePlanner([RouteDefinition("Yard", "Mine", ("MAIN-1",),
                                         (("A", "diverging"),), verified=True)]).plan(
        1, "Yard", "Mine", zones={"MAIN-1": None}, reservations={"MAIN-1": None},
        turnouts={"A": None})
    commands = []
    dispatcher.attach_turnout_command(lambda turnout, position: commands.append((turnout, position)))
    with pytest.raises(RuntimeError):
        dispatcher._align_turnouts(plan)
    assert commands == [("A", "diverging")]
    dispatcher.set_turnout_feedback("A", "diverging")
    dispatcher._align_turnouts(plan)


def test_dispatcher_request_queue_and_manual_takeover_are_explicit():
    dispatcher = Dispatcher()
    request = dispatcher.submit_request(1, "Yard")
    assert request["state"] == "PENDING"
    assert dispatcher.snapshot()["pending_requests"]
    dispatcher.manual_takeover(1)
    assert dispatcher.trains[1].control_mode == "manual"
    assert dispatcher.trains[1].velocity == 0
    assert dispatcher.cancel_request(1)
