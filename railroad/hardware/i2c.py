"""Safe I2C boundary. The bus is opened only when an explicit backend is used."""
from __future__ import annotations


class MockI2CBus:
    def __init__(self): self.registers: dict[tuple[int, int], int] = {}
    def read_byte_data(self, address, register): return self.registers.get((address, register), 0)
    def write_byte_data(self, address, register, value): self.registers[(address, register)] = value & 0xFF
    def write_word_data(self, address, register, value): self.registers[(address, register)] = value & 0xFFFF


class I2CBus:
    def __init__(self, bus: int = 1, enabled: bool = False, backend=None):
        self.bus, self.enabled, self.backend = bus, bool(enabled), backend

    def require_enabled(self):
        if not self.enabled or self.backend is None:
            raise RuntimeError("hardware I2C is disabled or unavailable")
        return self.backend

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
