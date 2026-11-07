import time
from threading import Lock

import pytest

from railroad.transport.estop import (
    ALL_TRAINS, DEFAULT_PERIOD_S, ESTOP_FLAG, EmergencyStop, create_bench_sender
)
from railroad.transport.udp import Command


class FakeSender:
    def __init__(self):
        self.frames = []
        self.lock = Lock()

    def send(self, cmd):
        with self.lock:
            self.frames.append(cmd)

    def snapshot(self):
        with self.lock:
            return list(self.frames)


def test_estop_broadcasts_immediately_and_repeats_until_clear():
    fake = FakeSender()
    stop = EmergencyStop(fake, period_s=0.02)
    try:
        stop.activate()
        immediate = fake.snapshot()
        assert len(immediate) >= 1
        assert immediate[0].train_id == ALL_TRAINS
        assert immediate[0].speed == 0
        assert immediate[0].flags == ESTOP_FLAG
        assert Command.decode(immediate[0].encode()) == immediate[0]
        time.sleep(0.075)
        frames = fake.snapshot()
        assert len(frames) >= 3
        assert all(f.speed == 0 and f.flags == ESTOP_FLAG for f in frames)
        assert len(set(f.sequence for f in frames)) == len(frames)
        stop.clear()
        count = len(fake.snapshot())
        time.sleep(0.055)
        assert len(fake.snapshot()) == count
        assert not stop.armed
    finally:
        stop.shutdown()


def test_commands_blocked_during_estop_and_after_clear_until_rearm():
    fake = FakeSender()
    stop = EmergencyStop(fake, period_s=0.02)
    try:
        with pytest.raises(RuntimeError):
            stop.send_motion(1, 80)
        stop.rearm()
        stop.send_motion(1, 80)
        stop.activate()
        with pytest.raises(RuntimeError):
            stop.send_motion(1, 80)
        with pytest.raises(RuntimeError):
            stop.rearm()
        stop.clear()
        with pytest.raises(RuntimeError):
            stop.send_motion(1, 80)
        stop.rearm()
        stop.send_motion(1, 45)
        assert fake.snapshot()[-1].speed == 45
    finally:
        stop.shutdown()


def test_network_not_enabled_implicitly():
    with pytest.raises(RuntimeError):
        create_bench_sender()
