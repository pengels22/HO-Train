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
    controller: str = ""
    tag: str = ""
    configuration_status: str = ""


class HardwareRegistry:
    def __init__(self, entries: Iterable[IOEntry], *, reserved_bcm: Iterable[int] = ()):
        self.entries = tuple(entries)
        self.reserved_bcm = frozenset(reserved_bcm)

    @classmethod
    def from_config(cls, config: dict[str, Any], io_rows: Iterable[dict[str, Any]] | None = None) -> "HardwareRegistry":
        raw = config.get("io_registry", [])
        entries = []
        for item in raw:
            entry = IOEntry(**item)
            controller = entry.controller
            if entry.device_type == "mcp23017":
                controller = "inputs1" if entry.address == 0x20 else ("inputs2" if entry.address == 0x21 else controller)
            entries.append(IOEntry(**{**entry.__dict__, "controller": controller}))
        entries.extend(cls._physical_inventory(config, entries))
        registry = cls(entries, reserved_bcm=config.get("reserved_bcm_pins", []))
        return registry.apply_ui_rows(io_rows or [])

    @staticmethod
    def _physical_inventory(config: dict[str, Any], existing: list[IOEntry]) -> list[IOEntry]:
        """Expand configured PCA/Nano boards into addressable physical channels."""
        boards = (config.get("i2c", {}) or {}).get("boards", {}) or {}
        seen = {(e.board, e.address, e.channel) for e in existing}
        result: list[IOEntry] = []
        for controller, board_name, address in (
            ("motion1", "motor_1", boards.get("motor_1")),
            ("motion2", "motor_2", boards.get("motor_2")),
        ):
            if address is None or any(e.address == int(address) and e.device_type == "pca9685" for e in existing):
                continue
            for channel in range(16):
                key = (board_name, int(address), channel)
                if key in seen:
                    continue
                result.append(IOEntry(board=board_name, address=int(address), channel=channel,
                                      device_type="pca9685", function="unassigned",
                                      location="Raspberry Pi I2C", direction="output",
                                      polarity="active_high", active=False, spare=True,
                                      controller=controller))
                seen.add(key)
        for controller, board_name, address in (
            ("inputs1", "sensors_1", boards.get("sensors_1")),
            ("inputs2", "sensors_2", boards.get("sensors_2")),
        ):
            if address is None or sum(e.address == int(address) and e.device_type == "mcp23017" for e in existing) >= 16:
                continue
            for channel in tuple(f"GPA{i}" for i in range(8)) + tuple(f"GPB{i}" for i in range(8)):
                key = (board_name, int(address), channel)
                if key in seen:
                    continue
                result.append(IOEntry(board=board_name, address=int(address), channel=channel,
                                      device_type="mcp23017", function="unassigned",
                                      location="Raspberry Pi I2C", direction="input",
                                      polarity="active_low", active=False, spare=True,
                                      controller=controller))
                seen.add(key)
        if not any(e.board == "nano_ir" for e in existing):
            for channel in range(1, 13):
                result.append(IOEntry(board="nano_ir", address=None, channel=f"CH{channel}",
                                      device_type="nano_esp32", function="unassigned",
                                      location="Nano ESP IR receiver", direction="input",
                                      polarity="active_high", active=False, spare=True,
                                      controller="ir"))
        return result

    def apply_ui_rows(self, rows: Iterable[dict[str, Any]]) -> "HardwareRegistry":
        """Apply persisted editor metadata to matching physical entries."""
        lookup = {}
        for i, entry in enumerate(self.entries):
            if not entry.controller:
                continue
            logical = f"CH{int(entry.channel) + 1}" if entry.controller.startswith("motion") and isinstance(entry.channel, int) else None
            lookup[(entry.controller, str(entry.channel))] = i
            if logical:
                lookup[(entry.controller, logical)] = i
        for index, entry in enumerate(self.entries):
            if entry.controller.startswith("inputs") and isinstance(entry.channel, str):
                number = (int(entry.channel[3:]) if entry.channel.startswith("GPA") else 8 + int(entry.channel[3:])) + 1
                lookup[(entry.controller, f"CH{number}")] = index
            elif entry.controller == "ir":
                lookup[(entry.controller, str(entry.channel))] = index
        for row in rows:
            key = (str(row.get("controller", "")), str(row.get("channel", "")))
            index = lookup.get(key)
            if index is None:
                continue
            current = self.entries[index]
            device = str(row.get("device_type", "")) or current.device_type
            tag = str(row.get("tag", ""))
            status = str(row.get("configuration_status", ""))
            bias = str(row.get("bias", ""))
            polarity = "active_low" if bias == "Pull-up (internal)" else current.polarity
            self.entries = self.entries[:index] + (IOEntry(
                **{**current.__dict__, "device_type": device, "tag": tag,
                   "configuration_status": status, "polarity": polarity,
                   "active": device not in {"", "Unassigned"},
                   "spare": device in {"", "Unassigned"}}
            ),) + self.entries[index + 1:]
        return self

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
