class DRV8833:
    """Signed two-channel motor driver using an injected PWM backend."""
    def __init__(self, pwm, channel_pair: tuple[int, int], enabled: bool = False):
        self.pwm, self.channel_pair, self.enabled = pwm, channel_pair, bool(enabled)
        if len(channel_pair) != 2 or channel_pair[0] == channel_pair[1]:
            raise ValueError("DRV8833 requires two distinct PWM channels")
        if self.enabled:
            self.safe_stop()
    def command(self, speed: int) -> None:
        if not self.enabled: raise RuntimeError("motor hardware is disabled")
        if not -255 <= speed <= 255: raise ValueError("motor speed must be -255..255")
        forward, reverse = self.channel_pair
        write = getattr(self.pwm, "set_duty", None)
        if write is None:  # compatibility with the original injected test double
            write = lambda channel, duty: self.pwm.set_pwm(channel, 0, duty)
        write(forward, speed if speed > 0 else 0)
        write(reverse, -speed if speed < 0 else 0)
    def safe_stop(self):
        if self.enabled: self.command(0)
