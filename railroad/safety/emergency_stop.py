class EmergencyStop:
    def __init__(self): self.active = False
    def engage(self) -> None: self.active = True
    def reset(self) -> None: self.active = False
