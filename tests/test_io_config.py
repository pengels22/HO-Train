import csv

import pytest

from railroad.api import server
from railroad.dispatcher import Dispatcher, SafetyError


def test_io_config_is_written_as_pi_csv_atomically(tmp_path, monkeypatch):
    target = tmp_path / "config" / "io_config.csv"
    monkeypatch.setattr(server, "IO_CONFIG_PATH", target)
    rows = server._save_io_config([
        {"controller": "mega", "channel": "CH1", "device_type": "Motor",
         "tag": "1A", "configuration_status": "H-Bridge Motor 1", "bias": ""},
        {"controller": "ir", "channel": "CH1", "device_type": "IR Receiver",
         "tag": "Mine", "configuration_status": "configured", "bias": "No bias"},
    ])
    assert rows[0]["tag"] == "1A"
    with target.open(newline="", encoding="utf-8") as stream:
        saved = list(csv.DictReader(stream))
    assert saved[1]["controller"] == "ir"
    assert server._read_io_config() == saved


def test_io_config_rejects_unknown_controller_or_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "IO_CONFIG_PATH", tmp_path / "io.csv")
    with pytest.raises(ValueError, match="unknown I/O controller"):
        server._save_io_config([{"controller": "turntable", "channel": "CH1"}])
    with pytest.raises(ValueError, match="invalid channel"):
        server._save_io_config([{"controller": "mega", "channel": "GPIO1"}])


def test_default_io_inventory_is_physical_and_complete():
    import yaml
    hardware = yaml.safe_load((server.ROOT / "config/hardware.yaml").read_text())
    rows = server._default_io_config(hardware)
    assert len(rows) == 69
    assert rows[0]["board"] == "mega2560"
    assert rows[0]["physical_channel"] == "D46"
    assert rows[0]["tag"] == "M1_forward"
    assert rows[1]["tag"] == "M1_reverse"
    assert rows[16]["physical_channel"] == "D14"
    assert rows[44]["controller"] == "relay_nano"
    assert rows[-1]["controller"] == "ir"


def test_rejected_registry_does_not_overwrite_csv_or_create_backup(tmp_path, monkeypatch):
    from railroad.hardware.registry import HardwareRegistry

    target = tmp_path / "config" / "io_config.csv"
    monkeypatch.setattr(server, "IO_CONFIG_PATH", target)
    existing = server._save_io_config([
        {"controller": "mega", "channel": "CH1", "device_type": "Motor",
         "tag": "approved", "configuration_status": "configured"}
    ])
    before = target.read_bytes()
    warnings_before = list(server.IO_MIGRATION_WARNINGS)

    def reject_candidate(cls, hardware, rows=None):
        raise ValueError("candidate registry rejected")

    with monkeypatch.context() as patch:
        patch.setattr(HardwareRegistry, "from_config", classmethod(reject_candidate))
        with pytest.raises(ValueError, match="candidate registry rejected"):
            server._save_io_config([
                {"controller": "mega", "channel": "CH2", "device_type": "Servo",
                 "tag": "unapproved"}
            ], backup=True)
    assert target.read_bytes() == before
    assert server._read_io_config() == existing
    assert server.IO_MIGRATION_WARNINGS == warnings_before
    assert not target.with_suffix(target.suffix + ".bak").exists()


def test_api_rejects_invalid_registry_without_replacing_runtime_state(tmp_path, monkeypatch):
    from railroad.hardware.registry import HardwareRegistry

    target = tmp_path / "config" / "io_config.csv"
    monkeypatch.setattr(server, "IO_CONFIG_PATH", target)
    approved_rows, approved_registry = server._save_io_config([
        {"controller": "mega", "channel": "CH1", "device_type": "Servo",
         "tag": "farm_gates"}
    ], with_registry=True)
    monkeypatch.setattr(server, "IO_CONFIG_STATE", approved_rows)
    monkeypatch.setattr(server, "IO_HARDWARE_REGISTRY", approved_registry)
    before = target.read_bytes()

    class Request:
        def _json_body(self):
            return {"rows": [{"controller": "mega", "channel": "CH2",
                              "device_type": "Servo", "tag": "candidate"}]}

        def _json_response(self, payload, status=200):
            self.payload, self.status = payload, status

    request = Request()

    def reject_candidate(cls, hardware, rows=None):
        raise ValueError("candidate registry rejected")

    with monkeypatch.context() as patch:
        patch.setattr(HardwareRegistry, "from_config", classmethod(reject_candidate))
        server.DashboardHandler._save_io_config(request)

    assert request.status == 400
    assert "candidate registry rejected" in request.payload["error"]
    assert target.read_bytes() == before
    assert server.IO_CONFIG_STATE is approved_rows
    assert server.IO_HARDWARE_REGISTRY is approved_registry


def test_successful_save_returns_same_validated_registry_for_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "IO_CONFIG_PATH", tmp_path / "io_config.csv")
    rows, registry = server._save_io_config([
        {"controller": "mega", "channel": "CH15", "device_type": "Servo",
         "tag": "farm_gates"}
    ], with_registry=True)
    assert server._read_io_config() == rows
    assert registry.require_valid() is registry
    first = next(entry for entry in registry.entries
                 if entry.controller == "mega" and entry.channel == "D44")
    assert first.tag == "farm_gates"
    assert first.address is None

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
