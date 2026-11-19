import csv

import pytest

from railroad.api import server
from railroad.dispatcher import Dispatcher, SafetyError


def test_io_config_is_written_as_pi_csv_atomically(tmp_path, monkeypatch):
    target = tmp_path / "config" / "io_config.csv"
    monkeypatch.setattr(server, "IO_CONFIG_PATH", target)
    rows = server._save_io_config([
        {"controller": "motion1", "channel": "CH1", "device_type": "Motor",
         "tag": "1A", "configuration_status": "H-Bridge Motor 1", "bias": ""},
        {"controller": "inputs1", "channel": "CH1", "device_type": "",
         "tag": "As", "configuration_status": "configured", "bias": "Pull-up (internal)"},
    ])
    assert rows[0]["tag"] == "1A"
    with target.open(newline="", encoding="utf-8") as stream:
        saved = list(csv.DictReader(stream))
    assert saved[1]["controller"] == "inputs1"
    assert server._read_io_config() == saved


def test_io_config_rejects_unknown_controller_or_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "IO_CONFIG_PATH", tmp_path / "io.csv")
    with pytest.raises(ValueError, match="unknown I/O controller"):
        server._save_io_config([{"controller": "turntable", "channel": "CH1"}])
    with pytest.raises(ValueError, match="invalid channel"):
        server._save_io_config([{"controller": "motion1", "channel": "GPIO1"}])


def test_default_io_inventory_is_physical_and_complete():
    import yaml
    hardware = yaml.safe_load((server.ROOT / "config/hardware.yaml").read_text())
    rows = server._default_io_config(hardware)
    assert len(rows) == 76
    assert rows[0]["board"] == "motor_1"
    assert rows[0]["physical_channel"] == "0"
    assert rows[0]["tag"] == "1A"
    assert rows[1]["tag"] == "1B"
    assert rows[32]["physical_channel"] == "GPA0"
    assert rows[-1]["controller"] == "ir"


def test_motion2_csv_migration_is_safe_idempotent_and_recoverable(tmp_path, monkeypatch):
    import yaml
    target = tmp_path / "io_config.csv"
    monkeypatch.setattr(server, "IO_CONFIG_PATH", target)
    old = [{"controller": "motion2", "channel": "CH1", "device_type": "Motor",
            "tag": "legacy motor", "configuration_status": "old", "bias": ""}]
    server._save_io_config(old)
    migrated = server._read_io_config()
    assert migrated[0]["controller"] == "servo"
    assert migrated[0]["device_type"] == "Unassigned"
    # Saving an already migrated row does not create another backup or change it.
    first = server._read_io_config()
    server._save_io_config(first, hardware=yaml.safe_load((server.ROOT / "config/hardware.yaml").read_text()), backup=True)
    assert server._read_io_config() == first
    assert target.with_suffix(target.suffix + ".bak").exists()


def test_servo_controller_rejects_motor_assignments(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "IO_CONFIG_PATH", tmp_path / "io.csv")
    with pytest.raises(ValueError, match="servo controller"):
        server._save_io_config([{"controller": "servo", "channel": "CH1", "device_type": "Motor"}])


def test_dispatcher_operator_controls_are_stateful_without_motion_output():
    dispatcher = Dispatcher()
    dispatcher.set_operator_mode("manual")
    dispatcher.start_dispatcher()
    dispatcher.run_cycle_once()
    dispatcher.stop_dispatcher()
    snapshot = dispatcher.snapshot()
    assert snapshot["operator_mode"] == "manual"
    assert snapshot["dispatcher_running"] is False
    assert snapshot["cycle_requests"] == 1
    with pytest.raises(SafetyError):
        dispatcher.set_operator_mode("service")
