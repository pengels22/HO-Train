"""Allow-listed USB serial controller registry for safety messages.

There is deliberately no USB discovery.  Only controller IDs and ports
registered by configuration may be opened, and each port is isolated from the
others so a disconnected controller cannot block UDP or its peers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class SerialPort(Protocol):
    def write(self, data: bytes) -> int | None: ...
    def close(self) -> None: ...


@dataclass
class RegisteredController:
    controller_id: str
    port_name: str
    connector: Callable[[str], SerialPort]
    port: SerialPort | None = None
    last_error: Exception | None = None

    def reconnect(self) -> SerialPort:
        if self.port is None:
            self.port = self.connector(self.port_name)
        return self.port

    def send_estop(self) -> None:
        try:
            self.reconnect().write(b"ESTOP\n")
            self.last_error = None
        except Exception as exc:  # one controller must not stop the fan-out
            self.last_error = exc
            self.port = None
            raise

    def close(self) -> None:
        if self.port is not None:
            try:
                self.port.close()
            finally:
                self.port = None


class ControllerRegistry:
    def __init__(self, controllers: list[RegisteredController] | None = None):
        self.controllers = controllers or []

    def send_estop(self) -> None:
        errors = []
        for controller in self.controllers:
            try:
                controller.send_estop()
            except Exception as exc:
                errors.append((controller.controller_id, exc))
        if errors:
            raise ControllerDeliveryError(errors)

    def close(self) -> None:
        for controller in self.controllers:
            controller.close()


class ControllerDeliveryError(OSError):
    def __init__(self, errors):
        self.errors = tuple(errors)
        super().__init__("USB E-Stop delivery failed: " + ", ".join(i for i, _ in self.errors))


def pyserial_connector(port_name: str, *, baudrate: int = 115200) -> SerialPort:
    """Open a configured port only when an explicit hardware runtime asks."""
    import serial  # optional dependency; never imported by simulation
    return serial.Serial(port_name, baudrate=baudrate, timeout=0)
