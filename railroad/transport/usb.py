"""Allow-listed USB serial controller registry for safety messages.

There is deliberately no USB discovery.  Only controller IDs and ports
registered by configuration may be opened, and each port is isolated from the
others so a disconnected controller cannot block UDP or its peers.
"""
from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Lock
from typing import Callable, Protocol
import json


class SerialPort(Protocol):
    def write(self, data: bytes) -> int | None: ...
    def readline(self) -> bytes: ...
    def close(self) -> None: ...


@dataclass
class RegisteredController:
    controller_id: str
    port_name: str
    connector: Callable[[str], SerialPort]
    port: SerialPort | None = None
    last_error: Exception | None = None
    connected: bool = False
    write_timeout_s: float = 0.05
    _executor: ThreadPoolExecutor | None = None
    _future: object | None = None
    _lock: Lock = None
    _write_lock: Lock = None

    def __post_init__(self):
        self._lock = Lock()
        self._write_lock = Lock()

    def _write_estop(self) -> None:
        with self._write_lock:
            self.reconnect().write(b"ESTOP\n")

    def reconnect(self) -> SerialPort:
        if self.port is None:
            self.port = self.connector(self.port_name)
            self.connected = True
        return self.port

    def send_estop(self) -> None:
        # One bounded worker per registered controller prevents a slow port
        # from delaying peers and prevents repeated E-Stop calls from queuing
        # stale packets without limit.
        with self._lock:
            if self._future is not None and not self._future.done():
                return
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"ho-usb-{self.controller_id}")
            self._future = self._executor.submit(self._write_estop)
            future = self._future
        try:
            future.result(timeout=self.write_timeout_s)
            self.last_error = None
            self.connected = True
        except TimeoutError:
            self.last_error = TimeoutError(f"{self.controller_id} E-Stop write exceeded deadline")
            raise self.last_error
        except Exception as exc:  # one controller must not stop the fan-out
            self.last_error = exc
            self.port = None
            self.connected = False
            raise

    def close(self) -> None:
        if self.port is not None:
            try:
                self.port.close()
            finally:
                self.port = None
                self.connected = False
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    def command(self, command: str, *, expect: str | None = None) -> str:
        """Send one registered-controller command and verify its reply."""
        if command not in {"STATUS", "REARM AUTH"}:
            raise ValueError("unsupported controller command")
        with self._write_lock:
            port = self.reconnect()
            port.write((command + "\n").encode("ascii"))
            reply = port.readline().decode("ascii", errors="replace").strip()
        if not reply or (expect and not reply.startswith(expect)):
            raise OSError(f"{self.controller_id} invalid controller reply: {reply!r}")
        self.last_error = None
        self.connected = True
        return reply


class ControllerRegistry:
    def __init__(self, controllers: list[RegisteredController] | None = None):
        self.controllers = controllers or []
        self.estop_active = False
        self._heartbeat_thread = None
        self._heartbeat_stop = None

    def set_estop_active(self, active: bool) -> None:
        self.estop_active = bool(active)

    def send_estop(self) -> None:
        errors = []
        if not self.controllers:
            return
        with ThreadPoolExecutor(max_workers=len(self.controllers), thread_name_prefix="ho-estop-fanout") as pool:
            futures = [(c, pool.submit(c.send_estop)) for c in self.controllers]
            for controller, future in futures:
                try:
                    future.result()
                except Exception as exc:
                    errors.append((controller.controller_id, exc))
        if errors:
            raise ControllerDeliveryError(errors)

    def close(self) -> None:
        self.stop_heartbeat()
        for controller in self.controllers:
            controller.close()

    def rearm_all(self) -> None:
        errors = []
        for controller in self.controllers:
            try:
                reply = controller.command("REARM AUTH", expect="{")
                status = json.loads(reply)
                if status.get("estop") or status.get("motor") or status.get("track_power"):
                    raise OSError(f"{controller.controller_id} did not report a safe rearm state")
            except Exception as exc:
                controller.last_error = exc
                controller.connected = False
                errors.append((controller.controller_id, exc))
        if errors:
            raise ControllerDeliveryError(errors)

    def start_heartbeat(self, period_s: float = 0.1) -> None:
        from threading import Event, Thread
        if self._heartbeat_thread is not None:
            return
        self._heartbeat_stop = Event()
        def loop():
            while not self._heartbeat_stop.wait(period_s):
                if self.estop_active:
                    continue
                for controller in self.controllers:
                    try:
                        controller.command("STATUS", expect="{")
                    except Exception as exc:
                        controller.last_error = exc
                        controller.connected = False
        self._heartbeat_thread = Thread(target=loop, name="ho-controller-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=1)
        self._heartbeat_thread = self._heartbeat_stop = None

    def status(self) -> list[dict]:
        return [{"id": c.controller_id, "port": c.port_name,
                 "connected": c.connected, "error": str(c.last_error) if c.last_error else None}
                for c in self.controllers]


class ControllerDeliveryError(OSError):
    def __init__(self, errors):
        self.errors = tuple(errors)
        super().__init__("USB E-Stop delivery failed: " + ", ".join(i for i, _ in self.errors))


def pyserial_connector(port_name: str, *, baudrate: int = 115200) -> SerialPort:
    """Open a configured port only when an explicit hardware runtime asks."""
    import serial  # optional dependency; never imported by simulation
    return serial.Serial(port_name, baudrate=baudrate, timeout=0, write_timeout=0.05)
