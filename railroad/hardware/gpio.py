"""Small GPIO abstraction with fail-closed E-Stop input semantics."""
from __future__ import annotations
from typing import Protocol


class GPIOBackend(Protocol):
    def setup_input(self, pin: int, *, pull_down: bool) -> None: ...
    def read(self, pin: int) -> int: ...


class GPIO:
    """Configurable input wrapper; no pins are touched unless enabled."""
    def __init__(self, enabled: bool = False, backend: GPIOBackend | None = None,
                 estop_pin: int | None = None):
        self.enabled = bool(enabled)
        self.backend = backend
        self.estop_pin = estop_pin
        if self.enabled and estop_pin is not None:
            self.configure_estop(estop_pin)

    def configure_estop(self, pin: int) -> None:
        if not isinstance(pin, int) or pin < 0:
            raise ValueError("E-Stop GPIO pin must be a non-negative integer")
        if self.enabled and self.backend is None:
            raise RuntimeError("GPIO backend is not configured")
        self.estop_pin = pin
        if self.enabled:
            self.backend.setup_input(pin, pull_down=True)

    @property
    def estop_pressed(self) -> bool:
        """COM=3.3V, NC=input: HIGH released, LOW pressed."""
        if not self.enabled or self.estop_pin is None or self.backend is None:
            return False
        return int(self.backend.read(self.estop_pin)) == 0

    def safe_stop(self) -> None:
        # Track power is interrupted by the physical contactor. Software has
        # no authority to re-energize it here.
        return None
