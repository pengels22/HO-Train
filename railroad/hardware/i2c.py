"""Safe I2C boundary with injectable backends.

The production backend is opened only when the caller explicitly enables I2C.
Tests and bench tools can inject :class:`MockI2CBus`; simulation never opens a
device file or writes a register.
"""
from __future__ import annotations


class MockI2CBus:
    def __init__(self):
        self.registers: dict[tuple[int, int], int] = {}
        self.writes: list[tuple[str, int, int, int]] = []
        self.closed = False

    def read_byte_data(self, address, register):
        return self.registers.get((address, register), 0) & 0xFF

    def write_byte_data(self, address, register, value):
        value &= 0xFF
        self.registers[(address, register)] = value
        self.writes.append(("byte", address, register, value))

    def write_word_data(self, address, register, value):
        value &= 0xFFFF
        self.registers[(address, register)] = value
        self.writes.append(("word", address, register, value))

    def write_quick(self, address):
        self.writes.append(("quick", address, 0, 0))

    def close(self):
        self.closed = True


class I2CBus:
    def __init__(self, bus: int = 1, enabled: bool = False, backend=None):
        self.bus, self.enabled, self.backend = bus, bool(enabled), backend

    @classmethod
    def open(cls, bus: int = 1, *, enabled: bool = False, backend=None) -> "I2CBus":
        """Open the Linux SMBus only for an explicit hardware configuration."""
        if not enabled:
            return cls(bus, enabled=False, backend=None)
        if backend is None:
            try:
                from smbus2 import SMBus
            except ImportError as exc:
                raise RuntimeError("hardware I2C requires smbus2") from exc
            backend = SMBus(bus)
        return cls(bus, enabled=True, backend=backend)

    def require_enabled(self):
        if not self.enabled or self.backend is None:
            raise RuntimeError("hardware I2C is disabled or unavailable")
        return self.backend

    def close(self):
        if self.backend is not None and hasattr(self.backend, "close"):
            self.backend.close()
        self.backend = None

    def read_byte_data(self, address: int, register: int) -> int:
        return int(self.require_enabled().read_byte_data(address, register)) & 0xFF

    def write_byte_data(self, address: int, register: int, value: int) -> None:
        self.require_enabled().write_byte_data(address, register, int(value) & 0xFF)

    def scan(self) -> list[int]:
        bus = self.require_enabled()
        return [address for address in range(0x03, 0x78)
                if _responds(bus, address)]


def _responds(bus, address: int) -> bool:
    try:
        if hasattr(bus, "write_quick"): bus.write_quick(address)
        else: bus.read_byte_data(address, 0)
        return True
    except Exception:
        return False
