class Interlocking:
    def __init__(self, active_turnouts: set[str] | None = None):
        self.active_turnouts = active_turnouts or set("ABCDEFG")
        self.alignment: dict[str, str] = {}

    def align(self, turnout: str, position: str, occupied: bool = False, uncertain: bool = False) -> None:
        if turnout not in self.active_turnouts:
            raise ValueError("turnout is passive or unknown")
        if occupied or uncertain:
            raise RuntimeError("unsafe to move turnout")
        self.alignment[turnout] = position
