from dataclasses import dataclass, field
from .throttle import Throttle

@dataclass
class Locomotive:
    train_id: int
    name: str = ""
    throttle: Throttle = field(default_factory=Throttle)
    section: str | None = None
    current_zone: str | None = None
    previous_zone: str | None = None
    target_zone: str | None = None
    reserved_zones: list[str] = field(default_factory=list)
    last_ir_checkpoint: str | None = None
    confidence: float = 0.0

class LocomotiveManager:
    def __init__(self, count: int = 4):
        self.trains = {i: Locomotive(i, f"Train {i}") for i in range(1, count + 1)}
        self.selected_id: int | None = None

    def select(self, train_id: int) -> Locomotive:
        if train_id not in self.trains:
            raise KeyError(train_id)
        self.selected_id = train_id
        return self.trains[train_id]

    def joystick_speed(self, speed: int) -> None:
        if self.selected_id is None:
            return
        self.trains[self.selected_id].throttle.take_manual_control(speed)
