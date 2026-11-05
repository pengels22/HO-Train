from dataclasses import dataclass

def clamp_speed(value: int) -> int:
    return max(-255, min(255, int(value)))

@dataclass
class Throttle:
    speed: int = 0
    target: str = "NONE"
    mode: str = "AUTOMATIC"

    def set_speed(self, speed: int) -> None:
        self.speed = clamp_speed(speed)

    def take_manual_control(self, requested_speed: int = 0) -> None:
        # Safe takeover: selection never inherits a previous train's throttle.
        self.mode = "MANUAL"
        self.target = "MANUAL"
        self.speed = clamp_speed(requested_speed)

    def release_manual_control(self, restore_target: str = "NONE") -> None:
        self.mode = "AUTOMATIC"
        self.target = restore_target
