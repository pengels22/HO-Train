import time
from threading import Lock

import pytest

from railroad.dispatcher import Dispatcher, SafetyError
from railroad.transport.estop import ALL_TRAINS, ESTOP_FLAG, EmergencyStop


class FakeSender:
    def __init__(self):
        self.frames = []
        self.lock = Lock()

    def send(self, command):
        with self.lock:
            self.frames.append(command)


def test_global_stop_immediately_stops_all_and_blocks_motion_until_rearm():
    sender = FakeSender()
    estop = EmergencyStop(sender, period_s=0.02)
    dispatcher = Dispatcher()
    dispatcher.attach_estop(estop, require_rearm=True)
    try:
        with pytest.raises(SafetyError):
            dispatcher.command_motion(1, 100)
        dispatcher.rearm()
        dispatcher.command_motion(1, 100)
        dispatcher.command_motion(2, 80)
        dispatcher.stop_all("missed checkpoint")
        assert [dispatcher.trains[n].velocity for n in range(1, 5)] == [0, 0, 0, 0]
        assert sender.frames[-1].train_id == ALL_TRAINS
        assert sender.frames[-1].flags == ESTOP_FLAG
        dispatcher.clear_stop()
        assert not dispatcher.estop_active
        with pytest.raises(SafetyError):
            dispatcher.command_motion(1, 100)
        dispatcher.rearm()
        dispatcher.command_motion(1, 25)
        assert dispatcher.trains[1].velocity == 25
    finally:
        estop.shutdown()


def test_safety_global_stop_repeats_and_packet_loss_does_not_clear_latch():
    sender = FakeSender()
    estop = EmergencyStop(sender, period_s=0.02)
    dispatcher = Dispatcher()
    dispatcher.attach_estop(estop, require_rearm=False)
    try:
        dispatcher.trains[1].expected_checkpoint = "IR-1"
        dispatcher.trains[1].checkpoint_deadline = 1
        dispatcher.check_deadlines(now=2)
        first_count = len(sender.frames)
        assert dispatcher.global_stop and dispatcher.estop_active
        time.sleep(0.055)
        assert len(sender.frames) >= first_count + 2
        # Simulate lost later packets: the local sender/receiver latch remains.
        with pytest.raises(SafetyError):
            dispatcher.clear_stop()
        assert dispatcher.estop_active
        dispatcher.trains[1].expected_checkpoint = None
        dispatcher.trains[1].checkpoint_deadline = None
        dispatcher.clear_stop()
        assert not dispatcher.estop_active
        assert dispatcher.snapshot()["motion_armed"] is False
        with pytest.raises(SafetyError):
            dispatcher.command_motion(1, 50)
    finally:
        estop.shutdown()


def test_one_broadcast_targets_multiple_locomotives_and_startup_sender_is_disarmed():
    sender = FakeSender()
    estop = EmergencyStop(sender, period_s=0.02)
    try:
        assert not estop.armed
        estop.activate()
        assert sender.frames[-1].train_id == ALL_TRAINS
        assert sender.frames[-1].speed == 0
        assert sender.frames[-1].flags == ESTOP_FLAG
    finally:
        estop.shutdown()
