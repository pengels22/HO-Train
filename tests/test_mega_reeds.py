from pathlib import Path
import pytest
import yaml
from railroad.dispatcher import Dispatcher
from railroad.hardware.mega_reeds import MegaReedReader
from railroad.hardware.reed import ReedState

CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/firmata_layout.yaml").read_text())


class Pin:
    def register_callback(self, cb):
        self.cb = cb
    def enable_reporting(self):
        self.reporting = True
    def send(self, value):
        self.cb(value)


class Board:
    board = object()
    def __init__(self):
        self.pins = {}
    def pin(self, number, mode):
        assert mode == "u"
        return self.pins.setdefault(number, Pin())


def fixture():
    clock = [0.]
    board = Board()
    dispatcher = Dispatcher()
    reader = MegaReedReader(board, CONFIG["mega"]["reed_pins"],
                            dispatcher.handle_reed_event, clock=lambda: clock[0])
    reader.start()
    return clock, board, dispatcher, reader


def send(clock, board, reader, pin, level, at, settle=None):
    clock[0] = at
    board.pins[pin].send(level)
    if settle is not None:
        clock[0] = settle
        return reader.poll()
    return []


def test_28_inputs_and_h_reed_events():
    clock, board, d, r = fixture()
    assert len(board.pins) == 28
    assert all(p.reporting for p in board.pins.values())
    send(clock, board, r, 35, 1, 0, .02)
    send(clock, board, r, 35, 0, 1, 1.02)
    send(clock, board, r, 35, 1, 2, 2.02)
    assert d.reed_states["turnout_H_common"] == "OPEN"
    assert d.reed_pulse_counts["turnout_H_common"] == 1


def test_bounce_and_multiple_car_events():
    clock, board, d, r = fixture()
    send(clock, board, r, 36, 1, 0, .03)
    send(clock, board, r, 36, 0, 1)
    send(clock, board, r, 36, 1, 1.005, 1.1)
    assert d.reed_pulse_counts.get("turnout_H_straight", 0) == 0
    for t, v in [(2, 0), (2.1, 1), (2.3, 0), (2.4, 1)]:
        send(clock, board, r, 36, v, t)
    clock[0] = 2.5
    assert [e.state for e in r.poll()] == [
        ReedState.CLOSED, ReedState.OPEN, ReedState.CLOSED, ReedState.OPEN]
    assert d.reed_pulse_counts["turnout_H_straight"] == 2


def test_open_does_not_authorize_automatic_return():
    clock, board, d, r = fixture()
    commands = []
    d.attach_turnout_command(lambda t, p: commands.append((t, p)))
    d.enable_turnout_auto_return()
    d.turnout_auto_return.command_position("H", "diverging")
    send(clock, board, r, 37, 1, 0, .03)
    send(clock, board, r, 37, 0, 1, 1.03)
    send(clock, board, r, 37, 1, 2, 2.03)
    assert d.poll_turnout_returns(now=5, route_holds=set(), occupied=set(), connected=True) == ()
    d.turnout_tail_confirmed("H", exit_reed="turnout_H_divergent")
    assert d.poll_turnout_returns(now=5, route_holds=set(), occupied=set(), connected=True) == ("H",)


def test_overflow_fails_closed():
    clock, board, d, r = fixture()
    r.max_pending = 1
    board.pins[14].send(0)
    board.pins[14].send(1)
    with pytest.raises(RuntimeError, match="overflow"):
        r.poll()
