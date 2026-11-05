from typing import Protocol

class HardwareOutput(Protocol):
    def safe_stop(self) -> None: ...

class SimulationOutput:
    def __init__(self): self.stopped = True
    def safe_stop(self) -> None: self.stopped = True
