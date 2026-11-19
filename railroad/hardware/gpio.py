"""Generic optional GPIO input abstraction; no physical stop input."""
from __future__ import annotations
from typing import Protocol

class GPIOBackend(Protocol):
    def setup_input(self, pin: int, *, pull_down: bool) -> None: ...
    def read(self, pin: int) -> int: ...

class GPIO:
    def __init__(self, enabled: bool = False, backend: GPIOBackend | None = None):
        self.enabled = bool(enabled)
        self.backend = backend

    def read_input(self, pin: int) -> int:
        if not self.enabled or self.backend is None:
            raise RuntimeError("GPIO backend is not enabled")
        if not isinstance(pin, int) or pin < 0:
            raise ValueError("invalid GPIO pin")
        return int(self.backend.read(pin))
