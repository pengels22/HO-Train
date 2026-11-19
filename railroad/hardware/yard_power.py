"""Safe three-circuit yard power adapter with no invented GPIO mappings."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class YardOutput:
    track: str
    sections: tuple[str, ...]
    pin: str | int | None = None
    active_high: bool = True


class YardPowerAdapter:
    def __init__(self, outputs, writer: Callable[[YardOutput, bool], None] | None = None):
        self.outputs = {str(item.track): item for item in outputs}
        self.writer = writer
        self.requested = {str(i): False for i in (1, 2, 3)}
        self.commanded = {str(i): False for i in (1, 2, 3)}
        self.verified = {str(i): False for i in (1, 2, 3)}
        self.faults: dict[str, str] = {}
        self._validate_inventory()
        for track, output in self.outputs.items():
            if output.pin is None:
                self.faults[track] = "UNASSIGNED"

    @classmethod
    def from_config(cls, config, writer=None):
        outputs = [YardOutput(str(row["track"]), tuple(str(section) for section in row.get("sections", ())),
                              row.get("gpio"), bool(row.get("active_high", True)))
                   for row in config.get("yard_outputs", [])]
        return cls(outputs, writer)

    def _validate_inventory(self):
        if set(self.outputs) != {"1", "2", "3"}:
            raise ValueError("yard power requires exactly tracks 1, 2, and 3")
        if self.outputs["1"].sections != ("1A", "1B"):
            raise ValueError("track 1 must control shared stalls 1A and 1B")
        if self.outputs["2"].sections != ("2",) or self.outputs["3"].sections != ("3",):
            raise ValueError("tracks 2 and 3 must each control one stall")

    def set_power(self, track: str, enabled: bool):
        track = str(track)
        if track not in self.outputs:
            raise ValueError(f"unknown yard track: {track}")
        enabled = bool(enabled)
        self.requested[track] = enabled
        output = self.outputs[track]
        if output.pin is None:
            self.faults[track] = "UNASSIGNED"
            self.commanded[track] = False
            if not enabled:
                return
            raise RuntimeError(f"yard track {track} output is unassigned")
        if self.writer is None:
            self.faults[track] = "yard output writer is unavailable"
            raise RuntimeError(f"yard track {track} output writer is unavailable")
        try:
            self.writer(output, enabled)
        except Exception as exc:
            self.faults[track] = str(exc)
            raise
        self.commanded[track] = enabled
        self.faults.pop(track, None)

    def status(self):
        return {"requested": self.requested.copy(), "commanded": self.commanded.copy(),
                "verified": self.verified.copy(), "faults": self.faults.copy(),
                "outputs": {track: {"sections": list(output.sections),
                                    "pin": output.pin,
                                    "active_high": output.active_high,
                                    "state": self.faults.get(track, "READY")}
                            for track, output in self.outputs.items()}}
