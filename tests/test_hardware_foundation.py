from pathlib import Path
import yaml

from railroad.hardware.i2c import I2CBus
from railroad.hardware.registry import HardwareRegistry
from railroad.hardware.reed import ReedDebouncer, ReedState


ROOT = Path(__file__).parents[1]


def test_registry_has_station_inputs_and_unassigned_turnout_input_channels():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    registry = HardwareRegistry.from_config(config).require_valid()
    inputs = [e for e in registry.entries if e.device_type == "mcp23017"]
    assert len(inputs) == 32
    assert sum(e.spare for e in inputs) == 25
    assert not any("turnout_H" in e.function for e in inputs)


def test_final_controller_assignments_keep_m5_fleet_and_xiao_accessories_distinct():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    assert [item["type"] for item in config["locomotive_controllers"]] == ["m5_atom_echo"] * 4
    accessories = {item["id"]: item["type"] for item in config["controller_transport"]["serial_controllers"]}
    assert accessories == {
        "turntable": "xiao_esp32_c6_turntable",
        "tipper": "xiao_esp32_c6_tipper",
    }


def test_two_pca9685_architecture_has_seven_motors_two_servos_and_relay_turnouts():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    boards = config["i2c"]["boards"]
    assert boards == {"motor_1": 0x40, "servo": 0x41, "sensors_1": 0x20, "sensors_2": 0x21}
    motors = yaml.safe_load((ROOT / "config/motors.yaml").read_text())["motors"]
    servos = yaml.safe_load((ROOT / "config/servos.yaml").read_text())["servos"]
    motor_channels = [channel for item in motors.values() for channel in item["channels"]]
    servo_channels = [item["channel"] for item in servos.values()]
    assert len(motors) == 7 and len(motor_channels) == 14 and len(set(motor_channels)) == 14
    assert len(servos) == 2 and len(set(servo_channels)) == 2
    assert set(range(16)) - set(motor_channels) == {14, 15}
    assert set(range(16)) - set(servo_channels) == {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}
    assert "turnout_H" not in servos


def test_hardware_startup_reports_each_declared_i2c_board_unavailable(monkeypatch):
    import railroad.api.server as server
    monkeypatch.setattr(server.I2CBus, "open", classmethod(
        lambda cls, bus=1, **kwargs: (_ for _ in ()).throw(OSError("no I2C bus"))))
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    assert server._start_hardware_devices(config) is None
    assert set(server.I2C_DEVICES) == set()
    assert all(not item["connected"] for item in server.I2C_STATUS.values())
    assert all(item["state"] == "UNAVAILABLE" for item in server.I2C_STATUS.values())
    assert 0x42 not in {int(address) for address in config["i2c"]["boards"].values()}
    server._close_hardware_devices()


def test_registry_expands_physical_pca_and_nano_channels_and_applies_saved_metadata():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    registry = HardwareRegistry.from_config(config, [{
        "controller": "motion1", "channel": "CH1", "device_type": "Motor",
        "tag": "1A", "configuration_status": "motor 1 forward",
    }]).require_valid()
    first = next(entry for entry in registry.entries if entry.controller == "motion1" and entry.channel == 0)
    assert first.address == 0x40 and first.tag == "1A" and first.active
    assert sum(entry.controller == "motion1" for entry in registry.entries) == 16
    assert sum(entry.controller == "inputs1" for entry in registry.entries) == 16
    assert sum(entry.controller == "ir" for entry in registry.entries) == 12
    pca = [entry for entry in registry.entries if entry.device_type == "pca9685"]
    assert len(pca) == 32
    assert {entry.address for entry in pca} == {0x40, 0x41}
    assert sum(entry.assignment_type == "Motor" for entry in pca) == 1

    from railroad.api import server
    default_registry = HardwareRegistry.from_config(config, server._default_io_config(config))
    default_pca = [entry for entry in default_registry.entries if entry.device_type == "pca9685"]
    assert sum(entry.assignment_type == "Motor" for entry in default_pca) == 14
    assert sum(entry.assignment_type == "Servo" for entry in default_pca) == 2


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
