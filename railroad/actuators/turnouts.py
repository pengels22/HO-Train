class TurnoutController:
    def __init__(self, active: set[str] | None = None): self.active = active or set("ABCDEFG")
    def command(self, turnout: str, position: str) -> None:
        if turnout not in self.active: raise ValueError("only active turnouts may be commanded")
