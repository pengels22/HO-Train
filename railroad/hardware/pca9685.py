class PCA9685:
    """PCA9685 PWM backend. Construction and safe_stop never energize outputs."""
    MODE1, MODE2, PRESCALE = 0x00, 0x01, 0xFE
    def __init__(self, address: int, bus=None, enabled: bool = False, *, frequency_hz: int = 50):
        self.address, self.bus, self.enabled = address, bus, bool(enabled)
        if self.enabled and bus is None: raise RuntimeError("PCA9685 requires an I2C bus")
        self.frequency_hz = int(frequency_hz)
        if self.enabled:
            self._initialize()

    def _initialize(self):
        if self.frequency_hz <= 0:
            raise ValueError("PCA9685 frequency must be positive")
        # MODE2=totem-pole, MODE1=sleep while changing the prescale.
        self.bus.write_byte_data(self.address, self.MODE1, 0x10)
        prescale = round(25_000_000 / (4096 * self.frequency_hz) - 1)
        self.bus.write_byte_data(self.address, self.PRESCALE, max(3, min(255, prescale)))
        self.bus.write_byte_data(self.address, self.MODE1, 0x00)
        self.bus.write_byte_data(self.address, self.MODE2, 0x04)
        self.safe_stop()
    def set_pwm(self, channel: int, on: int, off: int) -> None:
        if not self.enabled or self.bus is None: raise RuntimeError("PWM hardware is disabled")
        if not 0 <= channel < 16: raise ValueError("PCA9685 channel must be 0..15")
        if not 0 <= on <= 4095 or not 0 <= off <= 4095:
            raise ValueError("PCA9685 PWM values must be 0..4095")
        base = 0x06 + 4 * channel
        for offset, value in enumerate((on, on >> 8, off, off >> 8)):
            self.bus.write_byte_data(self.address, base + offset, value)

    def set_duty(self, channel: int, duty: int) -> None:
        if not 0 <= duty <= 4095:
            raise ValueError("PCA9685 duty must be 0..4095")
        self.set_pwm(channel, 0, duty)

    def set_servo_angle(self, channel: int, angle: float, *, min_us: int = 500, max_us: int = 2500) -> None:
        if not 0 <= angle <= 180:
            raise ValueError("servo angle must be 0..180")
        pulse_us = min_us + (max_us - min_us) * angle / 180.0
        ticks = round(pulse_us * self.frequency_hz * 4096 / 1_000_000)
        self.set_duty(channel, max(0, min(4095, ticks)))
    def safe_stop(self):
        if self.enabled:
            for channel in range(16): self.set_pwm(channel, 0, 0)
