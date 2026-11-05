from dataclasses import dataclass

@dataclass(frozen=True)
class JoystickMapping:
    dead_zone: int = 20
    minimum: int = -255
    maximum: int = 255

    def normalize_axis(self, raw: int) -> int:
        raw = max(-32768, min(32767, raw))
        if -self.dead_zone <= raw <= self.dead_zone:
            return 0
        if raw > self.dead_zone:
            return round((raw - self.dead_zone) * 255 / (32767 - self.dead_zone))
        return round((raw + self.dead_zone) * 255 / (32768 - self.dead_zone))

    def map_buttons(self, pressed: set[int]) -> int | None:
        for button in range(2, 6):
            if button in pressed:
                return button - 1
        return None
