"""Validated, declarative Raspberry Pi hardware I/O registry.

The registry is intentionally side-effect free: loading and validating it never
opens I2C or changes a GPIO.  A separate commissioning step may use the
validated entries to construct drivers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class IOEntry:
    board: str
    address: int | None
    channel: str | int
    device_type: str
    function: str
    location: str
    direction: str
    polarity: str
    active: bool = True
    spare: bool = False
    bcm: int | None = None


class HardwareRegistry:
    def __init__(self, entries: Iterable[IOEntry], *, reserved_bcm: Iterable[int] = ()):
        self.entries = tuple(entries)
        self.reserved_bcm = frozenset(reserved_bcm)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "HardwareRegistry":
        raw = config.get("io_registry", [])
        entries = [IOEntry(**item) for item in raw]
        return cls(entries, reserved_bcm=config.get("reserved_bcm_pins", []))

    def validate(self) -> list[str]:
        errors: list[str] = []
        seen: set[tuple[str, int | None, str | int]] = set()
        for entry in self.entries:
            key = (entry.board, entry.address, entry.channel)
            if key in seen:
                errors.append(f"duplicate I/O mapping: {key}")
            seen.add(key)
            if entry.bcm is not None and entry.bcm in self.reserved_bcm:
                errors.append(f"BCM GPIO {entry.bcm} is reserved")
            if entry.device_type == "gpio" and entry.address is not None:
                errors.append(f"GPIO entry {entry.function} must not have I2C address")
            if entry.device_type != "gpio" and entry.bcm is not None:
                errors.append(f"I2C entry {entry.function} must not have BCM pin")
            if entry.direction not in {"input", "output", "bidirectional"}:
                errors.append(f"invalid direction for {entry.function}: {entry.direction}")
            if entry.polarity not in {"active_low", "active_high", "none"}:
                errors.append(f"invalid polarity for {entry.function}: {entry.polarity}")
        return errors

    def require_valid(self) -> "HardwareRegistry":
        errors = self.validate()
        if errors:
            raise ValueError("invalid hardware registry: " + "; ".join(errors))
        return self

    def by_function(self, function: str) -> IOEntry:
        matches = [entry for entry in self.entries if entry.function == function]
        if len(matches) != 1:
            raise KeyError(function)
        return matches[0]

    def as_table(self) -> list[dict[str, Any]]:
        return [entry.__dict__.copy() for entry in self.entries]
