"""Turntable safety primitives shared by simulation and a future controller adapter."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TurntablePulseCounter:
    """Count four vehicle magnets per end with bounce and post-train cooldown."""
    lockout_s: float = 0.250
    cooldown_s: float = 0.500
    count_a: int = 0
    count_b: int = 0
    last_a: float | None = None
    last_b: float | None = None
    cooldown_until_a: float = 0.0
    cooldown_until_b: float = 0.0
    active_a: bool = False
    active_b: bool = False
    fault: str | None = None

    def pulse(self, end: str, now: float) -> int:
        if end not in {"A", "B"}:
            raise ValueError("turntable end must be A or B")
        last = self.last_a if end == "A" else self.last_b
        cooldown = self.cooldown_until_a if end == "A" else self.cooldown_until_b
        count = self.count_a if end == "A" else self.count_b
        if count >= 4 and now >= cooldown:
            raise RuntimeError(f"unexpected extra vehicle pulse at turntable end {end}")
        if now < cooldown or (last is not None and now - last < self.lockout_s):
            return count
        if end == "A":
            self.last_a = now; self.count_a += 1
            if self.count_a == 4: self.cooldown_until_a = now + self.cooldown_s
            return self.count_a
        self.last_b = now; self.count_b += 1
        if self.count_b == 4: self.cooldown_until_b = now + self.cooldown_s
        return self.count_b

    def reset(self, end: str | None = None) -> None:
        if end not in {None, "A", "B"}:
            raise ValueError("turntable end must be A or B")
        if end in {None, "A"}: self.count_a = 0; self.last_a = None; self.cooldown_until_a = 0
        if end in {None, "B"}: self.count_b = 0; self.last_b = None; self.cooldown_until_b = 0
        if end in {None, "A"}: self.active_a = False
        if end in {None, "B"}: self.active_b = False
        if end is None: self.fault = None

    def signal(self, end: str, active: bool, now: float) -> int:
        """Process a debounced digital level; only inactive->active counts."""
        if end not in {"A", "B"}:
            raise ValueError("turntable end must be A or B")
        was_active = self.active_a if end == "A" else self.active_b
        if end == "A": self.active_a = active
        else: self.active_b = active
        if not active:
            count = self.count_a if end == "A" else self.count_b
            if was_active and count == 4:
                if end == "A": self.cooldown_until_a = max(self.cooldown_until_a, now + self.cooldown_s)
                else: self.cooldown_until_b = max(self.cooldown_until_b, now + self.cooldown_s)
            return count
        if was_active:
            return self.count_a if end == "A" else self.count_b
        try:
            return self.pulse(end, now)
        except RuntimeError as exc:
            self.fault = str(exc)
            raise

    def complete(self, end: str) -> bool:
        if end not in {"A", "B"}: raise ValueError("turntable end must be A or B")
        return (self.count_a if end == "A" else self.count_b) == 4
