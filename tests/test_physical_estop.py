import time
from threading import Lock

import pytest

from railroad.dispatcher import Dispatcher, SafetyError
from railroad.hardware.gpio import GPIO
from railroad.safety.emergency_stop import EmergencyStop as PhysicalEmergencyStop
from railroad.transport.estop import EStopFanout, EmergencyStop, ESTOP_FLAG, ALL_TRAINS
from railroad.transport.usb import ControllerRegistry, RegisteredController
from railroad.transport.udp import Command


class FakeGPIOBackend:
    def __init__(self, value=1): self.value, self.setup = value, []
    def setup_input(self, pin, *, pull_down): self.setup.append((pin, pull_down))
    def read(self, pin): return self.value


class FakePort:
    def __init__(self): self.writes = []; self.closed = False
    def write(self, data): self.writes.append(data); return len(data)
    def close(self): self.closed = True


class FakeUDP:
    def __init__(self): self.commands = []; self.lock = Lock()
    def send(self, command):
        with self.lock: self.commands.append(command)


def test_gpio_low_is_pressed_and_simulation_is_silent():
    backend = FakeGPIOBackend(1)
    gpio = GPIO(enabled=True, backend=backend, estop_pin=17)
    assert backend.setup == [(17, True)]
    assert not gpio.estop_pressed
    backend.value = 0
    assert gpio.estop_pressed
    assert not GPIO(enabled=False, estop_pin=17).estop_pressed


def test_udp_and_each_registered_usb_controller_receive_independently():
    udp, good, bad = FakeUDP(), FakePort(), FakePort()
    def connect_good(port): return good
    def connect_bad(port): raise OSError("disconnected")
    registry = ControllerRegistry([
        RegisteredController("good", "/dev/good", connect_good),
        RegisteredController("bad", "/dev/bad", connect_bad),
    ])
    fanout = EStopFanout(udp, registry)
    with pytest.raises(OSError):
        fanout.send(Command(ALL_TRAINS, 1, 0, flags=ESTOP_FLAG))
    assert len(udp.commands) == 1
    assert good.writes == [b"ESTOP\n"]
    assert registry.controllers[1].last_error is not None


def test_usb_estop_repeats_with_udp_while_active():
    udp, port = FakeUDP(), FakePort()
    registry = ControllerRegistry([RegisteredController("c1", "/dev/c1", lambda _: port)])
    stop = EmergencyStop(EStopFanout(udp, registry), period_s=0.02)
    try:
        stop.activate(); time.sleep(0.055); stop.clear()
        assert len(udp.commands) >= 3
        assert len(port.writes) >= 3
        assert all(frame.flags == ESTOP_FLAG for frame in udp.commands)
        assert all(data == b"ESTOP\n" for data in port.writes)
    finally:
        stop.shutdown()


def test_physical_activation_bypasses_debounce_and_release_does_not_rearm():
    backend = FakeGPIOBackend(1)
    gpio = GPIO(enabled=True, backend=backend, estop_pin=9)
    udp = FakeUDP()
    estop = EmergencyStop(udp, period_s=0.02)
    dispatcher = Dispatcher(); dispatcher.attach_estop(estop, require_rearm=False)
    dispatcher.attach_physical_estop(lambda: gpio.estop_pressed)
    monitor = PhysicalEmergencyStop(gpio, dispatcher)
    try:
        backend.value = 0
        started = time.monotonic()
        monitor.poll_once()
        assert time.monotonic() - started < 0.25
        assert dispatcher.global_stop and dispatcher.trains[1].velocity == 0
        assert udp.commands[-1].flags == ESTOP_FLAG
        backend.value = 1
        monitor.poll_once()
        assert not estop.active
        dispatcher.clear_stop()
        # Releasing the physical switch is not sufficient; the motion latch
        # remains until an explicit operator rearm.
        with pytest.raises(SafetyError): dispatcher.command_motion(1, 20)
    finally:
        estop.shutdown()


def test_accessory_stop_fault_does_not_block_udp_delivery():
    udp = FakeUDP(); estop = EmergencyStop(udp, period_s=0.02)
    dispatcher = Dispatcher(); dispatcher.attach_estop(estop, require_rearm=False)
    called = []
    def broken_tipper(): called.append(True); raise OSError("tipper offline")
    dispatcher.attach_accessory_stops(tipper=broken_tipper)
    try:
        dispatcher.stop_all("operator")
        assert called and len(udp.commands) == 1
        with pytest.raises(SafetyError): dispatcher.clear_stop()
    finally:
        estop.shutdown()
