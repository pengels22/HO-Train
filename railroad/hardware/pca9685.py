class PCA9685:
    """PCA9685 PWM backend. Construction and safe_stop never energize outputs."""
    MODE1, PRESCALE = 0x00, 0xFE
    def __init__(self, address: int, bus=None, enabled: bool = False):
        self.address, self.bus, self.enabled = address, bus, bool(enabled)
        if self.enabled and bus is None: raise RuntimeError("PCA9685 requires an I2C bus")
    def set_pwm(self, channel: int, on: int, off: int) -> None:
        if not self.enabled or self.bus is None: raise RuntimeError("PWM hardware is disabled")
        if not 0 <= channel < 16: raise ValueError("PCA9685 channel must be 0..15")
        base = 0x06 + 4 * channel
        for offset, value in enumerate((on, on >> 8, off, off >> 8)):
            self.bus.write_byte_data(self.address, base + offset, value)
    def safe_stop(self):
        if self.enabled:
            for channel in range(16): self.set_pwm(channel, 0, 0)
