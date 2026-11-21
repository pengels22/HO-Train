from pathlib import Path
import yaml

from railroad.hardware.registry import HardwareRegistry
from railroad.hardware.reed import ReedDebouncer, ReedState


ROOT = Path(__file__).parents[1]


def test_registry_has_station_inputs_and_unassigned_turnout_input_channels():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    registry = HardwareRegistry.from_config(config).require_valid()
    inputs = [e for e in registry.entries if e.controller == "mega" and e.direction == "input"]
    assert len(inputs) == 28
    assert inputs[0].channel == "D14"
    assert inputs[-1].channel == "D41"
    assert not any(e.address is not None for e in registry.entries)


def test_final_controller_assignments_keep_m5_fleet_and_xiao_accessories_distinct():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    assert [item["type"] for item in config["locomotive_controllers"]] == ["m5_atom_echo"] * 4
    accessories = {item["id"]: item["type"] for item in config["controller_transport"]["serial_controllers"]}
    assert accessories == {
        "turntable": "xiao_esp32_c6_turntable",
        "tipper": "xiao_esp32_c6_tipper",
    }


def test_firmata_architecture_has_seven_motors_two_servos_and_relay_turnouts():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    firmata = yaml.safe_load((ROOT / "config/firmata_layout.yaml").read_text())
    assert config["firmata"]["enabled"] is True
    assert len(firmata["mega"]["motor_outputs"]) == 7
    assert set(firmata["mega"]["crossing_servos"]) == {"farm_gates", "town_gates"}
    assert {name: item for name, item in firmata["relay_nano"]["turnout_direction_select"].items()} == {
        name: f"D{index}" for index, name in enumerate("ABCDEFGH", 2)
    }

    registry = HardwareRegistry.from_config(config).require_valid()
    assert not any(entry.address is not None for entry in registry.entries)
    assert all(entry.board in {"mega2560", "nano_classic", "nano_esp32"}
               for entry in registry.entries)


def test_firmata_runtime_keeps_missing_relay_nano_independent():
    from railroad.hardware.firmata import FirmataControllerManager
    layout = yaml.safe_load((ROOT / "config/firmata_layout.yaml").read_text())
    layout["enabled"] = True
    layout["mega"]["port"] = None
    layout["relay_nano"]["port"] = None
    statuses = FirmataControllerManager(layout).connect_all()
    assert statuses["mega"].connected is False  # no hardware opened in tests
    assert statuses["relay_nano"].connected is False
    assert "persistent USB path" in statuses["relay_nano"].error


def test_registry_expands_firmata_channels_and_applies_saved_metadata():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    registry = HardwareRegistry.from_config(config, [{
        "controller": "mega", "channel": "CH1", "device_type": "Motor",
        "tag": "1A", "configuration_status": "motor 1 forward",
    }]).require_valid()
    first = next(entry for entry in registry.entries if entry.controller == "mega" and entry.channel == "D46")
    assert first.address is None and first.tag == "1A" and first.active
    assert sum(entry.controller == "mega" for entry in registry.entries) == 44
    assert sum(entry.controller == "relay_nano" for entry in registry.entries) == 11
    assert sum(entry.controller == "ir" for entry in registry.entries) == 14

    from railroad.api import server
    rows = server._default_io_config(config)
    assert len(rows) == 69
    assert sum(row["controller"] == "mega" for row in rows) == 44
    assert sum(row["controller"] == "relay_nano" for row in rows) == 11
    assert sum(row["controller"] == "ir" for row in rows) == 14


def test_reed_requires_stable_open_close_cycle_and_counts_long_contact_once():
    reed = ReedDebouncer("A", debounce_ms=10)
    assert reed.update(True, 0.0) == []
    assert reed.update(True, 0.011)[0].state is ReedState.CLOSED
    assert reed.update(False, 1.0) == []
    event = reed.update(False, 1.011)[0]
    assert event.state is ReedState.OPEN and event.pulse_number == 1
    assert event.duration_s > 1.0


def test_reed_bounce_does_not_double_count():
    reed = ReedDebouncer("A", debounce_ms=10)
    for closed, timestamp in ((True, 0), (False, .002), (True, .004), (True, .02), (False, .03), (True, .035), (False, .06), (False, .071)):
        reed.update(closed, timestamp)
    assert reed.pulses == 1
