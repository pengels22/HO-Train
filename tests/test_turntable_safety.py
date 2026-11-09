import pytest

from railroad.automation.tipper import SafeTipperAdapter, Tipper
from railroad.routing.interlocking import Interlocking
from railroad.turntable import TurntablePulseCounter


def test_turnout_h_accepts_only_supported_alignments():
    interlocking = Interlocking()
    interlocking.align("H", "straight")
    with pytest.raises(ValueError):
        interlocking.align("H", "unknown")


def test_turntable_counts_four_pulses_per_end_with_lockout_and_cooldown():
    counter = TurntablePulseCounter()
    for now in (0.0, 0.1, 0.3, 0.6, 0.9):
        counter.pulse("A", now)
    assert counter.complete("A")
    assert counter.count_a == 4  # the 0.1 pulse is bounce; the other four are accepted
    assert counter.count_b == 0
    counter.pulse("B", 0.0)
    assert counter.count_b == 1


def test_tipper_adapter_stops_motor_and_decoupler_independently():
    class Hardware:
        def __init__(self): self.calls = []
        def stop_motor(self): self.calls.append("motor")
        def set_decoupler(self, enabled): self.calls.append(("decoupler", enabled))
        def rearm(self): self.calls.append("rearm")

    hardware = Hardware()
    adapter = SafeTipperAdapter(hardware)
    adapter.stop()
    assert hardware.calls == ["motor", ("decoupler", False)]
    adapter.rearm()
    assert hardware.calls[-1] == "rearm"


def test_simulation_tipper_remains_usable_without_hardware_outputs():
    tipper = Tipper()
    tipper.start(True, True)
    tipper.rotate(1)
