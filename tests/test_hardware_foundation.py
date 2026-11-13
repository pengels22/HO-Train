from pathlib import Path
import yaml

from railroad.hardware.i2c import I2CBus, MockI2CBus
from railroad.hardware.mcp23017 import MCP23017
from railroad.hardware.registry import HardwareRegistry
from railroad.hardware.reed import ReedDebouncer, ReedState
from railroad.hardware.pca9685 import PCA9685


ROOT = Path(__file__).parents[1]


def test_confirmed_registry_has_25_inputs_and_seven_spares_without_duplicates():
    config = yaml.safe_load((ROOT / "config/hardware.yaml").read_text())
    registry = HardwareRegistry.from_config(config).require_valid()
    inputs = [e for e in registry.entries if e.device_type == "mcp23017"]
    assert len(inputs) == 32
    assert sum(e.spare for e in inputs) == 7
    assert not any("turnout_H" in e.function for e in inputs)


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
