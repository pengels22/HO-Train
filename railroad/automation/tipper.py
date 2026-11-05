from enum import Enum

class TipperState(str, Enum):
    IDLE="IDLE"; LOADING="LOADING"; ROTATING="ROTATING"; RETURNING="RETURNING"; UNLOADING="UNLOADING"; FAULT="FAULT"

class Tipper:
    def __init__(self):
        self.state = TipperState.IDLE
        self.fault: str | None = None
        self.direction = 0

    def start(self, front_low: bool, back_low: bool) -> None:
        if self.state != TipperState.IDLE or not (front_low and back_low):
            raise RuntimeError("tipper interlock not satisfied")
        self.state = TipperState.LOADING

    def rotate(self, direction: int) -> None:
        if self.state != TipperState.LOADING or direction not in (-1, 1):
            raise RuntimeError("tipper not ready to rotate")
        self.direction = direction; self.state = TipperState.ROTATING

    def complete(self) -> None:
        if self.state not in (TipperState.ROTATING, TipperState.RETURNING, TipperState.UNLOADING):
            raise RuntimeError("invalid completion")
        self.state = TipperState.IDLE

    def fail(self, reason: str) -> None:
        self.fault = reason; self.state = TipperState.FAULT
