import time
from threading import Lock

import pytest

from railroad.transport.locomotive import (
    ALL_TRAINS, DEFAULT_PERIOD_S, GLOBAL_STOP_FLAG, LocomotiveCommandTransport, create_bench_sender
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
    stop = LocomotiveCommandTransport(fake, period_s=0.02)
    try:
        stop.activate()
        immediate = fake.snapshot()
        assert len(immediate) >= 1
        assert immediate[0].train_id == ALL_TRAINS
        assert immediate[0].speed == 0
        assert immediate[0].flags == GLOBAL_STOP_FLAG
        assert Command.decode(immediate[0].encode()) == immediate[0]
        time.sleep(0.075)
        frames = fake.snapshot()
        assert len(frames) >= 3
        assert all(f.speed == 0 and f.flags == GLOBAL_STOP_FLAG for f in frames)
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
    stop = LocomotiveCommandTransport(fake, period_s=0.02)
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


def test_latest_command_repeats_for_locomotive_watchdog():
    fake = FakeSender()
    transport = LocomotiveCommandTransport(fake, period_s=0.02, start_armed=True)
    try:
        transport.send_motion(1, 80)
        transport.send_motion(2, -35)
        time.sleep(0.075)
        frames = fake.snapshot()
        train_one = [frame for frame in frames if frame.train_id == 1]
        train_two = [frame for frame in frames if frame.train_id == 2]
        assert len(train_one) >= 3
        assert len(train_two) >= 3
        assert all(frame.speed == 80 for frame in train_one)
        assert all(frame.speed == -35 for frame in train_two)
        assert len({frame.sequence for frame in frames}) == len(frames)
    finally:
        transport.shutdown()


def test_network_not_enabled_implicitly():
    with pytest.raises(RuntimeError):
        create_bench_sender()
