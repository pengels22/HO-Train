import json
import time

import pytest

from railroad.automation.tipper import TipperSerialController
from railroad.turntable import TurntableController, TurntableState


def four_pulses(controller, entry=True):
    for index in range(4):
        now = index * 0.3
        (controller.entry_pulse if entry else controller.exit_pulse)(now, True)
        (controller.entry_pulse if entry else controller.exit_pulse)(now + 0.01, False)


def test_complete_loaded_turntable_lifecycle():
    table = TurntableController("HOME")
    table.authorize_entry(track_power=True, train_stopped=True, consist_count=4)
    assert table.state == TurntableState.TRAIN_ENTERING
    four_pulses(table)
    table.confirm_loaded(train_stopped=True, clearance_verified=True, now=2.0)
    table.begin_rotation()
    assert table.target_alignment == "ROTATED" and not table.track_power
    table.reach_alignment("ROTATED")
    table.set_polarity("normal")
    table.authorize_exit(track_power=True, train_stopped=True)
    four_pulses(table, entry=False)
    table.confirm_empty(train_stopped=True, now=2.0)
    assert table.state == TurntableState.EMPTY_READY
    assert not table.track_power


def test_turntable_estop_interruption_never_resumes_automatically():
    table = TurntableController("ROTATED")
    table.authorize_entry(track_power=True, train_stopped=True, consist_count=4)
    table.emergency_stop()
    assert table.state == TurntableState.FAULT and not table.track_power
    with pytest.raises(RuntimeError): table.begin_rotation()
    table.rearm(authorized=True, alignment="ROTATED", faults_clear=True)
    assert table.state == TurntableState.EMPTY_READY


def test_tipper_serial_requires_positive_motor_and_decoupler_ack():
    class Port:
        def __init__(self, reply): self.reply = reply; self.writes = []
        def write(self, value): self.writes.append(value)
        def readline(self): return self.reply
    ok = Port(b'{"transaction":"tipper-1","ok":true,"motor":false,"decoupler":false}\n')
    controller = TipperSerialController(ok)
    controller.stop_motor()
    assert b'"command":"ESTOP"' in ok.writes[0]
    class SlowPort(Port):
        def readline(self):
            time.sleep(0.02)
            return b""
    slow = SlowPort(b"")
    with pytest.raises(TimeoutError): TipperSerialController(slow, response_timeout_s=0.001).command("STATUS")
