"""Optional pyFirmata2 board adapter, disabled until commissioned.

There is deliberately no output actuation at import or object construction.
StandardFirmata cannot guarantee safe coil pulses or fail-safe USB disconnect.
"""
from __future__ import annotations


class FirmataNotReady(RuntimeError):
    pass


class FirmataBoard:
    """Small injectable pyFirmata2 facade with explicit opt-in connection."""

    def __init__(self, *, kind: str, port: str | None, enabled: bool = False, factory=None):
        self.kind = kind
        self.port = port
        self.enabled = bool(enabled)
        self.factory = factory
        self.board = None

    def connect(self):
        if not self.enabled or not self.port:
            raise FirmataNotReady("Firmata requires commissioning enable and a verified serial port")
        if self.board is not None:
            return self.board
        if self.factory is None:
            try:
                from pyfirmata2 import Arduino, ArduinoMega
            except ImportError as exc:
                raise FirmataNotReady("Install optional dependency pyfirmata2") from exc
            factory = {"mega2560": ArduinoMega, "nano_classic": Arduino}.get(self.kind)
        else:
            factory = self.factory
        if factory is None:
            raise ValueError("Unsupported Firmata board")
        self.board = factory(self.port)
        return self.board

    def pin(self, number: int, mode: str):
        if self.board is None:
            raise FirmataNotReady("Board is not connected")
        if mode not in {"i", "o", "p", "s"}:
            raise ValueError("Unsupported pin mode")
        return self.board.get_pin(f"d:{int(number)}:{mode}")

    def close(self):
        if self.board is not None:
            try:
                self.board.exit()
            finally:
                self.board = None


def validate_pin_map(config: dict) -> list[str]:
    """Check the proposed allocation, not the physical wiring."""
    errors = []
    for controller_name in ("mega", "relay_nano"):
        controller = config[controller_name]
        allocations = {}
        def add(pin, owner):
            pin = str(pin)
            if pin in allocations:
                errors.append(f"{controller_name} {pin} assigned to {allocations[pin]} and {owner}")
            allocations[pin] = owner
        if controller_name == "mega":
            for pin, name in controller["reed_pins"].items():
                add(pin, name)
            for motor, outputs in controller["motor_outputs"].items():
                for direction in ("forward", "reverse"):
                    add(outputs[direction], f"{motor}_{direction}")
            for name, pin in controller["crossing_servos"].items():
                add(pin, name)
            if len(controller["reed_pins"]) != 28:
                errors.append("Mega must have 28 reed inputs")
        else:
            for name, pin in controller["turnout_direction_select"].items():
                add(pin, f"turnout_{name}")
            for name, pin in controller["yard_power"].items():
                add(pin, f"yard_{name}")
            if set(controller["turnout_direction_select"]) != set("ABCDEFGH"):
                errors.append("Relay Nano must enumerate A-H")
    return errors
