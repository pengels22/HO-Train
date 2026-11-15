"""Regression checks for locally isolated accessory faults and tipper wiring.

These tests perform no serial, GPIO, network, or physical motion.
"""
from pathlib import Path

from railroad.transport.estop import EStopFanout
from railroad.transport.udp import Command
from railroad.transport.usb import ControllerRegistry, RegisteredController


class RecordingSender:
    def __init__(self):
        self.transactions = []

    def send_rearm(self, transaction):
        self.transactions.append(transaction)

    def send(self, command: Command):
        raise AssertionError("send_rearm should be used")


def test_locomotive_rearm_not_blocked_by_disconnected_accessory():
    def disconnected(_port):
        raise OSError("tipper unplugged")

    tipper = RegisteredController("tipper", "/dev/not-connected", disconnected)
    registry = ControllerRegistry([tipper])
    registry.set_estop_active(True)
    sender = RecordingSender()
    fanout = EStopFanout(sender, registry)

    # Locomotive rearm must not open/rearm a faulted USB accessory.
    fanout.rearm("train-rearm-001")
    assert sender.transactions == ["train-rearm-001"]
    assert registry.estop_active is False
    assert tipper.port is None
    assert tipper.connected is False


def test_tipper_d10_assignment_and_ir_clearance_removed():
    # Config-to-firmware static regression: D10 is GPIO18 on XIAO ESP32-C6.
    root = Path(__file__).resolve().parents[1]
    config = (root / "config" / "tipper.yaml").read_text()
    firmware = (root / "firmware" / "tipper_esp32c6" / "tipper_esp32c6.ino").read_text()
    assert "decoupler_output: 18" in config
    assert "#define TIPPER_DECOUPLER_OUTPUT 18" in firmware
    assert "ir_front_clear:" not in config and "ir_back_clear:" not in config
    assert "TIPPER_IR_FRONT_CLEAR" not in firmware
    assert "TIPPER_IR_BACK_CLEAR" not in firmware
    assert "encoder_slots: 40" in config
    assert "encoder_wheel_diameter_in: 1.125" in config


def test_tipper_has_bounded_operator_calibration_and_active_low_d10():
    root = Path(__file__).resolve().parents[1]
    firmware = (root / "firmware" / "tipper_esp32c6" / "tipper_esp32c6.ino").read_text()
    config = (root / "config" / "tipper.yaml").read_text()
    assert "#define TIPPER_DECOUPLER_OUTPUT 18" in firmware
    assert "#define TIPPER_DECOUPLER_ACTIVE_HIGH 0" in firmware
    assert "decoupler_active_high: false" in config
    assert "JOG_DURATION_MS = 200" in firmware
    assert 'line == "JOG CW"' in firmware
    assert 'line == "MARK START"' in firmware
    assert 'line == "SET 120"' in firmware
    assert 'line == "HOME"' in firmware
    assert "estopLatched" not in firmware
    assert "TIPPER_ROTATION_COUNTS_PER_120_DEG" not in firmware


def test_yard_has_no_assigned_io_and_pi_gpio_is_unused():
    root = Path(__file__).resolve().parents[1]
    hardware = (root / "config" / "hardware.yaml").read_text()
    yard = (root / "config" / "yard_power.yaml").read_text()
    assert "relay_outputs: {}" in yard
    assert "bcm:" not in yard
    assert "reserved_bcm_pins:" not in hardware
    assert "yard_track_1_relay" not in hardware
    assert "yard_track_2_relay" not in hardware
    assert "yard_track_3_relay" not in hardware
