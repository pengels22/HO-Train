"""I²C adapter boundary. Real bus access is intentionally not initialized here."""
class I2CBus:
    def __init__(self, bus: int = 1, enabled: bool = False): self.bus, self.enabled = bus, enabled
    def require_enabled(self):
        if not self.enabled: raise RuntimeError("hardware I2C is disabled")
