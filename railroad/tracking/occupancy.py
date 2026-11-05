from enum import Enum
from dataclasses import dataclass

class OccupancyState(str, Enum):
    CLEAR = "CLEAR"; RESERVED = "RESERVED"; OCCUPIED = "OCCUPIED"; UNKNOWN = "UNKNOWN"; FAULT = "FAULT"

@dataclass
class Section:
    section_id: str
    neighbors: tuple[str, ...] = ()
    elevation: int = 0
    state: OccupancyState = OccupancyState.UNKNOWN
    reserved_by: int | None = None
    occupied_by: int | None = None

    def can_reserve(self, train_id: int) -> bool:
        return self.state in (OccupancyState.CLEAR, OccupancyState.RESERVED) and (self.reserved_by in (None, train_id)) and self.occupied_by in (None, train_id)
