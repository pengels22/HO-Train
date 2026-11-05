from dataclasses import dataclass, field
from railroad.tracking.occupancy import Section

@dataclass
class TrackGraph:
    sections: dict[str, Section] = field(default_factory=dict)
    turnouts: dict[str, str] = field(default_factory=dict)

    def add_section(self, section: Section) -> None:
        self.sections[section.section_id] = section

    def route_available(self, route: list[str], train_id: int) -> bool:
        return all(s in self.sections and self.sections[s].can_reserve(train_id) for s in route)

    def reserve(self, route: list[str], train_id: int) -> None:
        if not self.route_available(route, train_id):
            raise RuntimeError("route unavailable")
        for name in route:
            self.sections[name].reserved_by = train_id
            self.sections[name].state = self.sections[name].state.RESERVED

    def release(self, train_id: int) -> None:
        for section in self.sections.values():
            if section.reserved_by == train_id:
                section.reserved_by = None
                if section.occupied_by is None:
                    section.state = section.state.CLEAR
