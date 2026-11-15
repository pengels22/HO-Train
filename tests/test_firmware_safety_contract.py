from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_m5_rearm_has_random_boot_session_and_independent_telemetry_sequence():
    source = (ROOT / "firmware/locomotive_m5_atom_echo/locomotive_m5_atom_echo.ino").read_text()
    assert "esp_random()" in source
    assert "telemetrySequence++" in source
    assert "last_command_sequence" in source
    assert "lastRearmTransaction" in source
    assert "state != ESTOP_LATCHED && state != COMMUNICATION_FAULT" in source


def test_turntable_serial_parser_is_bounded_and_preserves_plain_estop():
    source = (ROOT / "firmware/turntable_esp32c6/turntable_esp32c6.ino").read_text()
    assert "MAX_SERIAL_LINE = 192" in source
    assert "serialOverflow" in source
    assert "line_too_long" in source
    assert 'line == "ESTOP"' in source
    assert "duplicate_transaction" in source
    assert "json_authorization_required" in source
