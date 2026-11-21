"""Pi-side turnout return controller. No hardware I/O on import."""
from dataclasses import dataclass
from typing import Callable

STANDARDS = {"A": "diverging", **{name: "straight" for name in "BCDEFGH"}}


def relay_input_level(turnout: str, position: str) -> int:
    """HIGH=NC=standard; LOW=NO=alternate; all relay modules active-low."""
    if turnout not in STANDARDS: raise KeyError(turnout)
    if position not in ("straight", "diverging"): raise ValueError(position)
    return int(position == STANDARDS[turnout])


@dataclass
class PendingReturn:
    exit_reed: str
    seen_closed: bool = False
    opened_at: float | None = None
    tail_confirmed: bool = False


class TurnoutAutoReturn:
    def __init__(self, command: Callable[[str, str], None], *, clearance_seconds: float = 1.0):
        if clearance_seconds <= 0: raise ValueError("clearance must be positive")
        self.command = command
        self.clearance_seconds = clearance_seconds
        self.positions = STANDARDS.copy()
        self.pending: dict[str, PendingReturn] = {}

    def command_position(self, turnout: str, position: str):
        relay_input_level(turnout, position)  # validate
        if self.positions[turnout] == position:
            return
        self.command(turnout, position)  # errors must not update commanded state
        self.positions[turnout] = position
        self.pending.pop(turnout, None)
        if position != STANDARDS[turnout]:
            suffix = "straight" if position == "straight" else "divergent"
            self.pending[turnout] = PendingReturn(f"turnout_{turnout}_{suffix}")

    def reed_event(self, sensor: str, *, closed: bool, now: float):
        for pending in self.pending.values():
            if sensor != pending.exit_reed: continue
            if closed:
                pending.seen_closed = True
                pending.opened_at = None
                pending.tail_confirmed = False
            elif pending.seen_closed and pending.opened_at is None:
                pending.opened_at = now

    def confirm_tail_clear(self, turnout: str, *, exit_reed: str):
        """Called only after dispatcher confirms the last car cleared this exit."""
        p = self.pending.get(turnout)
        if p and p.exit_reed == exit_reed and p.seen_closed and p.opened_at is not None:
            p.tail_confirmed = True

    def tick(self, now: float, *, route_holds: set[str] | None = None,
             occupied: set[str] | None = None, connected: bool = False) -> tuple[str, ...]:
        """Fail closed if connectivity or route/occupancy information is uncertain."""
        if not connected or route_holds is None or occupied is None: return ()
        restored = []
        for turnout, p in tuple(self.pending.items()):
            if (not p.tail_confirmed or p.opened_at is None
                    or now - p.opened_at < self.clearance_seconds
                    or turnout in route_holds or turnout in occupied):
                continue
            self.command(turnout, STANDARDS[turnout])
            self.positions[turnout] = STANDARDS[turnout]
            del self.pending[turnout]
            restored.append(turnout)
        return tuple(restored)
