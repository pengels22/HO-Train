"""Safe I2C boundary.

The production backend is opened only when the caller explicitly enables I2C.
Simulation never opens a device file or writes a register.  Hardware startup
reports absent boards as unavailable instead of fabricating a device response.
"""
from __future__ import annotations

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
