class DRV8833:
    def __init__(self, pwm, channel_pair: tuple[int, int], enabled: bool = False):
        self.pwm, self.channel_pair, self.enabled = pwm, channel_pair, bool(enabled)
    def command(self, speed: int) -> None:
        if not self.enabled: raise RuntimeError("motor hardware is disabled")
        if not -255 <= speed <= 255: raise ValueError("motor speed must be -255..255")
        forward, reverse = self.channel_pair
        self.pwm.set_pwm(forward, 0, speed if speed > 0 else 0)
        self.pwm.set_pwm(reverse, 0, -speed if speed < 0 else 0)
    def safe_stop(self):
        if self.enabled: self.command(0)
