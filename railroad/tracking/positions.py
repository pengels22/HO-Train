from dataclasses import dataclass
@dataclass
class TrainPosition:
    train_id: int
    checkpoint: str | None = None
    section: str | None = None
    direction: int = 0
    confidence: float = 0.0
