from types import SimpleNamespace
import pytest
from railroad.hardware.firmata import FirmataMegaOutputs, FirmataRelayOutputs, FirmataNotReady
from railroad.hardware.yard_power import YardPowerAdapter
from railroad.actuators.turnouts import TurnoutController
from railroad.hardware.turnout_return import TurnoutAutoReturn

class Board:
    def __init__(self): self.writes = []
    def pin(self, number, mode):
        return SimpleNamespace(write=lambda value: self.writes.append((number, mode, value)))

def test_pwm_and_digital_motor_magnitude():
    board = Board()
    manager = SimpleNamespace(boards={"mega": board}, status={"mega": SimpleNamespace(connected=True)},
        layout={"mega": {"motor_outputs": {"M2": {"forward": "D2", "reverse": "D3", "mode": "pwm"},
                "M1": {"forward": "D46", "reverse": "D47", "mode": "digital_full_speed"}}}})
    outputs = FirmataMegaOutputs(manager)
    outputs.motor("M2", -64)
    assert board.writes == [(2, "p", 0), (3, "p", 0), (3, "p", 64/255)]
    outputs.motor("M1", 64)
    assert board.writes[-1] == (46, "o", 1)
    manager.status["mega"].connected = False
    with pytest.raises(FirmataNotReady): outputs.motor("M2", 64)

def test_yard_mapping_and_polarity():
    board = Board()
    layout = {"relay_nano": {"yard_power": {"1": "D10", "2": "D11", "3": "D12"}}}
    manager = SimpleNamespace(boards={"relay_nano": board}, status={"relay_nano": SimpleNamespace(connected=True)}, layout=layout)
    relays = FirmataRelayOutputs(manager)
    hardware = {"yard_outputs": [{"track": 1, "sections": ["1A","1B"]}, {"track": 2, "sections": ["2"]}, {"track": 3, "sections": ["3"]}]}
    yard = YardPowerAdapter.from_firmata(hardware, layout, writer=lambda output, enabled: relays.yard_power(output.track, enabled))
    yard.set_power("1", True)
    yard.set_power("1", False)
    assert board.writes == [(10, "o", 0), (10, "o", 1)]
    assert yard.status()["verified"]["1"] is False

def test_h_inventory_and_repeat_command_preserves_pending():
    TurnoutController().command("H", "diverging")
    tracker = TurnoutAutoReturn(lambda *_: None)
    tracker.command_position("H", "diverging")
    pending = tracker.pending["H"]
    tracker.command_position("H", "diverging")
    assert tracker.pending["H"] is pending
