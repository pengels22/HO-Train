from pathlib import Path

import pytest
import yaml

from railroad.hardware.firmata import FirmataBoard, FirmataNotReady, validate_pin_map

CONFIG = Path(__file__).resolve().parents[1] / "config" / "firmata_layout.yaml"


def test_commissioned_pin_map_is_unique_with_optional_relay_nano():
    data = yaml.safe_load(CONFIG.read_text())
    assert data["enabled"] is True
    assert data["relay_nano"]["port"] is None
    assert validate_pin_map(data) == []
    assert list(data["mega"]["reed_pins"])[0] == "D14"
    assert list(data["mega"]["reed_pins"])[23] == "D37"
    assert data["mega"]["reed_pins"]["D35"] == "turnout_H_common"
    assert data["mega"]["reed_pins"]["D41"] == "town"
    assert len(data["relay_nano"]["turnout_direction_select"]) == 8


def test_firmata_requires_explicit_commissioning():
    with pytest.raises(FirmataNotReady):
        FirmataBoard(kind="mega2560", port="/dev/ttyFake", enabled=False).connect()


def test_firmata_adapter_uses_selected_board_and_pin_modes():
    class Stub:
        def __init__(self, port):
            self.port, self.requested, self.closed = port, [], False
        def get_pin(self, label):
            self.requested.append(label)
            return label
        def exit(self):
            self.closed = True
    board = FirmataBoard(kind="mega2560", port="/dev/test", enabled=True, factory=Stub)
    board.connect()
    assert board.pin(44, "s") == "d:44:s"
    board.close()
    assert board.board is None
