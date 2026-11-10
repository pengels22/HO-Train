import pytest
import time
import json

from railroad.dispatcher import Dispatcher
from railroad.transport.estop import EStopFanout, EmergencyStop
from railroad.transport.telemetry import ControllerHealthRegistry, LocomotiveTelemetry
from railroad.transport.usb import ControllerRegistry, RegisteredController


def telemetry(**overrides):
    values = dict(locomotive_id=1, state="ARMED", estop=False,
                  communication_fault=False, armed=True, speed=0,
                  sequence=7, session="boot-1", uptime_ms=100)
    values.update(overrides)
    return LocomotiveTelemetry(**values)


def test_locomotive_telemetry_is_versioned_and_requires_fresh_safe_state():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1], freshness_s=0.5)
    received = time.monotonic()
    health.update(telemetry().encode(), now=received)
    assert health.all_required_ready()
    assert health.status()[0]["session"] == "boot-1"
    health.freshness_s = 0.000001
    time.sleep(0.002)
    assert not health.all_required_ready()


def test_bad_or_unsafe_locomotive_telemetry_cannot_rearm():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    with pytest.raises(ValueError): health.update(b"bad")
    health.update(telemetry(estop=True).encode(), now=1.0)
    assert not health.all_required_ready()


def test_duplicate_and_out_of_order_telemetry_are_rejected():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    health.update(telemetry(sequence=4).encode(), now=1.0)
    with pytest.raises(ValueError):
        health.update(telemetry(sequence=4).encode(), now=1.1)
    with pytest.raises(ValueError):
        health.update(telemetry(sequence=3).encode(), now=1.2)


def test_operating_health_allows_nonzero_speed_but_rearm_does_not():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    now = time.monotonic()
    health.update(telemetry(speed=20, sequence=1).encode(), now=now)
    assert health.operating_ready()
    assert not health.rearm_ready()
    for sequence in range(2, 102):
        health.update(telemetry(speed=20 if sequence % 2 else -20, sequence=sequence).encode(), now=now + sequence / 1000)
        assert health.operating_ready()


def test_dispatcher_accepts_100_healthy_nonzero_commands():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    dispatcher = Dispatcher()
    dispatcher.attach_controller_health(health)
    now = time.monotonic()
    health.update(telemetry(sequence=1, speed=1).encode(), now=now)
    dispatcher._rearm_required = False
    for sequence in range(2, 102):
        speed = 30 if sequence % 2 else -30
        health.update(telemetry(sequence=sequence, speed=speed).encode(), now=now + sequence / 1000)
        dispatcher.command_motion(1, speed)
    assert dispatcher.trains[1].velocity == 30


def test_new_boot_session_invalidates_previous_health():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    failures = []
    health.on_failure = lambda controller, reason: failures.append((controller, reason))
    health.update(telemetry(sequence=9, session="old").encode(), now=1.0)
    health.update(telemetry(sequence=0, session="new").encode(), now=1.1)
    assert any("restart" in reason for _, reason in failures)
    assert not health.all_required_ready()


def test_retired_session_cannot_overwrite_current_session():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    health.update(telemetry(session="old", sequence=4).encode(), now=1.0)
    health.update(telemetry(session="new", sequence=0).encode(), now=1.1)
    with pytest.raises(ValueError, match="retired"):
        health.update(telemetry(session="old", sequence=5).encode(), now=1.2)


def test_controller_fault_requires_explicit_reconciliation():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    base = time.monotonic()
    health.update(telemetry(estop=True, state="ESTOP_LATCHED", sequence=1).encode(), now=base)
    health.update(telemetry(sequence=2).encode(), now=base + 0.1)
    assert not health.operating_ready()
    health.reconcile(1)
    assert health.operating_ready()


def test_telemetry_rejects_coercible_or_out_of_range_fields():
    packet = json.loads(telemetry().encode()[2:])
    packet["armed"] = 1
    with pytest.raises(ValueError):
        LocomotiveTelemetry.decode(b"HT" + json.dumps(packet).encode())


def test_rearm_requires_exact_fresh_transaction_ack():
    health = ControllerHealthRegistry(ControllerRegistry(), locomotive_ids=[1])
    base = time.monotonic()
    health.update(telemetry(state="DISARMED", armed=False, sequence=1).encode(), now=base)
    health.begin_rearm("rearm-new")
    health.update(telemetry(sequence=2, rearm_transaction="wrong").encode(), now=base + 0.1)
    assert not health.wait_for_rearm("rearm-new", timeout=0.001)
    health.update(telemetry(sequence=3, rearm_transaction="rearm-new").encode(), now=base + 0.2)
    assert health.wait_for_rearm("rearm-new", timeout=0.01)
    assert health.all_required_ready()
    packet = json.loads(telemetry().encode()[2:])
    packet["speed"] = 999
    with pytest.raises(ValueError):
        LocomotiveTelemetry.decode(b"HT" + json.dumps(packet).encode())


def test_dispatcher_rearm_requires_usb_safe_state_ack():
    class UDP:
        def send(self, command): pass
    class Port:
        def __init__(self): self.writes = []
        def write(self, data):
            self.writes.append(data)
            request = json.loads(data)
            self.reply = json.dumps({"controller": "turntable", "transaction": request["transaction"], "state": "EMPTY_READY", "estop": False, "motor": False, "track_power": False}).encode() + b"\n"
        def readline(self): return self.reply
        def close(self): pass
    port = Port()
    usb = ControllerRegistry([RegisteredController("turntable", "/dev/tt", lambda _: port)])
    health = ControllerHealthRegistry(usb)
    stop = EmergencyStop(EStopFanout(UDP(), usb), period_s=0.02)
    dispatcher = Dispatcher(); dispatcher.attach_estop(stop, require_rearm=True); dispatcher.attach_controller_health(health)
    try:
        dispatcher.rearm()
        dispatcher.command_motion(1, 10)
        assert dispatcher.trains[1].velocity == 10
    finally:
        stop.shutdown()
