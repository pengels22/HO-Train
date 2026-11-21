"""Optional pyFirmata2 board adapter, disabled until commissioned.

There is deliberately no output actuation at import or object construction.
StandardFirmata cannot guarantee safe coil pulses or fail-safe USB disconnect.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock, Thread
import time

from railroad.hardware.mega_reeds import MegaReedReader


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
        if mode not in {"i", "u", "o", "p", "s"}:
            raise ValueError("Unsupported pin mode")
        # StandardFirmata exposes INPUT_PULLUP as an input plus a HIGH write.
        # Keep the public `u` mode readable while using the pyFirmata2 pin API.
        pin = self.board.get_pin(f"d:{int(number)}:{'i' if mode == 'u' else mode}")
        if mode == "u":
            try:
                pin.write(1)
            except AttributeError:
                pass
        return pin

    def close(self):
        if self.board is not None:
            try:
                self.board.exit()
            finally:
                self.board = None


@dataclass
class FirmataStatus:
    controller: str
    kind: str
    port: str | None
    connected: bool = False
    commissioned: bool = False
    error: str | None = None
    last_success: float | None = None


class FirmataControllerManager:
    """Independent USB lifecycle for the commissioned Mega and relay Nano.

    Discovery never opens a port and construction never writes an output. The
    caller must enable the Firmata layout explicitly before `connect_all()`.
    Each board has independent status and reconnect handling.
    """

    def __init__(self, layout: dict, *, factories: dict | None = None,
                 clock=time.monotonic):
        self.layout = layout or {}
        self.enabled = bool(self.layout.get("enabled", False))
        self.clock = clock
        self.factories = factories or {}
        self.boards: dict[str, FirmataBoard] = {}
        self.status: dict[str, FirmataStatus] = {
            name: FirmataStatus(name, spec.get("board", "unknown"), spec.get("port"),
                                commissioned=self.enabled)
            for name, spec in (("mega", self.layout.get("mega", {})),
                               ("relay_nano", self.layout.get("relay_nano", {})))
        }
        self.reeds: MegaReedReader | None = None
        self._poll_stop: Event | None = None
        self._poll_thread: Thread | None = None
        self._lock = Lock()

    def connect_all(self) -> dict[str, FirmataStatus]:
        if not self.enabled:
            return self.status
        for name, spec in (("mega", self.layout.get("mega", {})),
                           ("relay_nano", self.layout.get("relay_nano", {}))):
            port = spec.get("port")
            if not port:
                self.status[name].error = "verified persistent USB path is not configured"
                continue
            board = FirmataBoard(kind=spec.get("board", ""), port=port,
                                 enabled=True, factory=self.factories.get(name))
            try:
                board.connect()
                self.boards[name] = board
                self.status[name].connected = True
                self.status[name].error = None
                self.status[name].last_success = self.clock()
                self._safe_initialize(name)
            except Exception as exc:
                self.status[name].connected = False
                self.status[name].error = str(exc)
                board.close()
        return self.status

    def _safe_initialize(self, name: str) -> None:
        """Initialize all outputs to their non-driving state."""
        board = self.boards[name]
        if name == "mega":
            spec = self.layout["mega"]
            for outputs in spec.get("motor_outputs", {}).values():
                for direction in ("forward", "reverse"):
                    pin = board.pin(_pin_number(outputs[direction]), "p" if outputs.get("mode") == "pwm" else "o")
                    pin.write(0)
            for pin_number in spec.get("crossing_servos", {}).values():
                board.pin(_pin_number(pin_number), "s").write(90)
        elif name == "relay_nano":
            spec = self.layout["relay_nano"]
            for pin_number in list(spec.get("turnout_direction_select", {}).values()) + list(spec.get("yard_power", {}).values()):
                board.pin(_pin_number(pin_number), "o").write(1)

    def start_reeds(self, on_event) -> bool:
        if "mega" not in self.boards:
            return False
        spec = self.layout["mega"]
        self.reeds = MegaReedReader(
            self.boards["mega"], spec["reed_pins"], on_event,
            debounce_ms=int(spec.get("reed_debounce_ms", 15)))
        self.reeds.start()
        self._poll_stop = Event()
        interval = max(0.001, int(spec.get("reed_reader_poll_ms", 10)) / 1000)
        def poll_loop():
            while self._poll_stop and not self._poll_stop.wait(interval):
                try:
                    self.reeds.poll()
                except Exception as exc:
                    self.status["mega"].error = str(exc)
                    break
        self._poll_thread = Thread(target=poll_loop, name="ho-mega-reeds", daemon=True)
        self._poll_thread.start()
        return True

    def close(self) -> None:
        if self._poll_stop:
            self._poll_stop.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
        self._poll_stop = self._poll_thread = None
        for board in self.boards.values():
            board.close()
        self.boards.clear()
        for status in self.status.values():
            status.connected = False

    def snapshot(self) -> dict[str, dict]:
        return {name: {"controller": value.controller, "kind": value.kind,
                       "port": value.port, "connected": value.connected,
                       "commissioned": value.commissioned, "error": value.error,
                       "last_success": value.last_success}
                for name, value in self.status.items()}


def _pin_number(value) -> int:
    text = str(value).upper()
    return int(text[1:]) if text.startswith("D") else int(text)


class FirmataMegaOutputs:
    """Exclusive-direction motor and crossing-servo boundary for the Mega."""

    def __init__(self, manager: FirmataControllerManager):
        self.manager = manager

    def _board(self):
        board = self.manager.boards.get("mega")
        if board is None:
            raise FirmataNotReady("Mega is not connected")
        return board

    def motor(self, motor: str, speed: int) -> None:
        spec = self.manager.layout["mega"]["motor_outputs"].get(motor)
        if spec is None:
            raise KeyError(motor)
        speed = max(-255, min(255, int(speed)))
        board = self._board()
        forward = board.pin(_pin_number(spec["forward"]), "p" if spec.get("mode") == "pwm" else "o")
        reverse = board.pin(_pin_number(spec["reverse"]), "p" if spec.get("mode") == "pwm" else "o")
        # Clear the opposite direction before asserting the requested side.
        forward.write(0)
        reverse.write(0)
        if speed > 0:
            forward.write(255 if spec.get("mode") == "pwm" else 1)
        elif speed < 0:
            reverse.write(255 if spec.get("mode") == "pwm" else 1)

    def servo(self, name: str, angle: float) -> None:
        pin_number = self.manager.layout["mega"]["crossing_servos"].get(name)
        if pin_number is None:
            raise KeyError(name)
        self._board().pin(_pin_number(pin_number), "s").write(max(0, min(180, float(angle))))


class FirmataRelayOutputs:
    """Maintained active-low turnout and three-section yard relay outputs."""

    def __init__(self, manager: FirmataControllerManager):
        self.manager = manager
        self.positions = {}

    def _board(self):
        board = self.manager.boards.get("relay_nano")
        if board is None:
            raise FirmataNotReady("relay Nano is not connected")
        return board

    def turnout(self, turnout: str, position: str) -> None:
        spec = self.manager.layout["relay_nano"]["turnout_direction_select"].get(turnout)
        if spec is None:
            raise KeyError(turnout)
        if position not in {"straight", "diverging"}:
            raise ValueError(position)
        # A's physical standard orientation is reversed; B-H use NC=straight.
        standard = "diverging" if turnout == "A" else "straight"
        active = position != standard
        self._board().pin(_pin_number(spec), "o").write(0 if active else 1)
        self.positions[turnout] = position

    def yard_power(self, track: str, enabled: bool) -> None:
        pin = self.manager.layout["relay_nano"]["yard_power"].get(str(track))
        if pin is None:
            raise KeyError(track)
        self._board().pin(_pin_number(pin), "o").write(0 if enabled else 1)


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
