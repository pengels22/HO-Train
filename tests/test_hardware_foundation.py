from pathlib import Path
import yaml

from railroad.hardware.i2c import I2CBus, MockI2CBus
from railroad.hardware.mcp23017 import MCP23017
from railroad.hardware.registry import HardwareRegistry
from railroad.hardware.reed import ReedDebouncer, ReedState
from railroad.hardware.pca9685 import PCA9685


ROOT = Path(__file__).parents[1]


def test_confirmed_registry_has_28_inputs_and_four_spares_without_duplicates():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    registry = HardwareRegistry.from_config(config).require_valid()
    inputs = [e for e in registry.entries if e.device_type == "mcp23017"]
    assert len(inputs) == 32
    assert sum(e.spare for e in inputs) == 4
    assert not any("turnout_H" in e.function for e in inputs)


def test_final_controller_assignments_keep_m5_fleet_and_xiao_accessories_distinct():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    assert [item["type"] for item in config["locomotive_controllers"]] == ["m5_atom_echo"] * 4
    accessories = {item["id"]: item["type"] for item in config["controller_transport"]["serial_controllers"]}
    assert accessories == {
        "turntable": "xiao_esp32_c6_turntable",
        "tipper": "xiao_esp32_c6_tipper",
    }


def test_two_pca9685_architecture_has_seven_motors_twelve_servos_and_six_spares():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    boards = config["i2c"]["boards"]
    assert boards == {"motor_1": 0x40, "servo": 0x41, "sensors_1": 0x20, "sensors_2": 0x21}
    motors = yaml.safe_load((ROOT / "config/motors.yaml").read_text())["motors"]
    servos = yaml.safe_load((ROOT / "config/servos.yaml").read_text())["servos"]
    motor_channels = [channel for item in motors.values() for channel in item["channels"]]
    servo_channels = [item["channel"] for item in servos.values()]
    assert len(motors) == 7 and len(motor_channels) == 14 and len(set(motor_channels)) == 14
    assert len(servos) == 12 and len(set(servo_channels)) == 12
    assert set(range(16)) - set(motor_channels) == {14, 15}
    assert set(range(16)) - set(servo_channels) == {8, 13, 14, 15}
    assert "turnout_H" not in servos


def test_hardware_startup_initializes_four_declared_i2c_boards_only(monkeypatch):
    import railroad.api.server as server
    mock = MockI2CBus()
    monkeypatch.setattr(server.I2CBus, "open", classmethod(lambda cls, bus=1, **kwargs: I2CBus(bus, True, mock)))
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    assert server._start_hardware_devices(config) is None
    assert set(server.I2C_DEVICES) == {"sensors_1", "sensors_2", "motor_1", "servo"}
    assert (0x40, 0x06) in mock.registers and mock.registers[(0x40, 0x08)] == 0
    assert (0x41, 0x06) in mock.registers and mock.registers[(0x41, 0x08)] == 0
    assert 0x42 not in {int(address) for address in config["i2c"]["boards"].values()}
    server._close_hardware_devices()


def test_mock_i2c_drivers_configure_inputs_and_stop_pwm():
    mock = MockI2CBus()
    bus = I2CBus(enabled=True, backend=mock)
    sensors = MCP23017(0x20, mock, enabled=True)
    mock.registers[(0x20, sensors.GPIOA)] = 0xFE
    assert sensors.read_inputs() & 0xFF == 0xFE
    pwm = PCA9685(0x40, mock, enabled=True)
    pwm.set_pwm(1, 0, 123)
    pwm.safe_stop()
    assert mock.registers[(0x40, 0x0A)] == 0


def test_mock_i2c_outputs_are_dependency_injected_and_start_safe():
    mock = MockI2CBus()
    pwm = PCA9685(0x40, mock, enabled=True)
    driver = __import__("railroad.hardware.drv8833", fromlist=["DRV8833"]).DRV8833(
        pwm, (0, 1), enabled=True)
    assert mock.registers[(0x40, 0x06)] == 0
    assert mock.registers[(0x40, 0x0A)] == 0
    driver.command(100)
    assert mock.registers[(0x40, 0x08)] == 100
    assert mock.registers[(0x40, 0x0C)] == 0
    driver.safe_stop()
    assert mock.registers[(0x40, 0x08)] == 0


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
    assert sum(entry.assignment_type == "Servo" for entry in default_pca) == 12


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
