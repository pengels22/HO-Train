"""Regression tests for dispatcher and local accessory stop transports.

The project has no physical stop input. These tests exercise the dispatcher
stop flag, locomotive STOP path, communication watchdog policy, accessory
isolation, and recovery without opening GPIO or energizing hardware.
"""
import time
from threading import Lock

import pytest

from railroad.dispatcher import Dispatcher, SafetyError
from railroad.transport.locomotive import (
    ALL_TRAINS, GLOBAL_STOP_FLAG, LocomotiveCommandTransport,
    LocomotiveStopFanout,
)
from railroad.transport.telemetry import ControllerHealthRegistry, LocomotiveTelemetry
from railroad.transport.udp import Command
from railroad.transport.usb import ControllerRegistry, RegisteredController


class FakeSender:
    def __init__(self):
        self.commands = []
        self.lock = Lock()

    def send(self, command):
        with self.lock:
            self.commands.append(command)

    def snapshot(self):
        with self.lock:
            return list(self.commands)


def test_dispatcher_global_stop_preserves_wire_flag_and_blocks_until_rearm():
    sender = FakeSender()
    transport = LocomotiveCommandTransport(sender, period_s=0.02)
    dispatcher = Dispatcher()
    dispatcher.attach_motion_transport(transport)
    try:
        dispatcher.rearm()
        dispatcher.command_motion(1, 80)
        dispatcher.stop_all("operator global stop")
        frame = sender.snapshot()[-1]
        assert (frame.train_id, frame.speed, frame.flags) == (ALL_TRAINS, 0, GLOBAL_STOP_FLAG)
        with pytest.raises(SafetyError):
            dispatcher.command_motion(1, 10)
        dispatcher.clear_stop()
        with pytest.raises(SafetyError):
            dispatcher.command_motion(1, 10)
        dispatcher.rearm()
        dispatcher.command_motion(1, 10)
        assert dispatcher.trains[1].velocity == 10
    finally:
        transport.shutdown()


def test_individual_locomotive_stop_is_zero_speed_without_global_stop():
    sender = FakeSender()
    transport = LocomotiveCommandTransport(sender, start_armed=True)
    dispatcher = Dispatcher()
    dispatcher.attach_motion_transport(transport, require_rearm=False)
    try:
        dispatcher.command_motion(1, 40)
        dispatcher.command_motion(2, 25)
        dispatcher.stop_train(1)
        assert dispatcher.trains[1].velocity == 0
        assert dispatcher.trains[2].velocity == 25
        assert not dispatcher.global_stop
    finally:
        transport.shutdown()


def test_watchdog_faults_only_moving_missing_locomotive():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1, 2], independent_locomotives=False)
    health.set_motion_provider(lambda: {1: False, 2: True})
    health.check_freshness(now=10.0)
    assert "locomotive-2:telemetry stale or missing" in health.failures()
    assert "locomotive-1:telemetry stale or missing" not in health.failures()


def test_local_accessory_stop_does_not_block_locomotive_stop_delivery():
    udp = FakeSender()
    registry = ControllerRegistry([RegisteredController("tipper", "/dev/missing", lambda _: (_ for _ in ()).throw(OSError("offline")))])
    fanout = LocomotiveStopFanout(udp, registry)
    dispatcher = Dispatcher()
    transport = LocomotiveCommandTransport(fanout, start_armed=True)
    dispatcher.attach_motion_transport(transport, require_rearm=False)
    called = []
    dispatcher.attach_accessory_stops(tipper=lambda: called.append(True))
    try:
        dispatcher.stop_all("operator global stop")
        assert called
        assert udp.snapshot()[-1].flags == GLOBAL_STOP_FLAG
    finally:
        transport.shutdown()


def test_unrelated_controller_disconnect_does_not_global_stop():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1, 2], independent_locomotives=True)
    dispatcher = Dispatcher()
    dispatcher.attach_controller_health(health)
    packet = LocomotiveTelemetry(
        locomotive_id=1, state="ARMED", estop=False, communication_fault=False,
        armed=True, speed=0, sequence=1, session="bench", uptime_ms=1,
    ).encode()
    health.update(packet, now=time.monotonic())
    health.check_freshness(now=time.monotonic())
    assert not dispatcher.global_stop
    assert dispatcher.trains[1].velocity == 0
