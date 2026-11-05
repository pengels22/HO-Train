from dataclasses import dataclass
@dataclass(frozen=True)
class ReceiverEvent:
    receiver_id: str
    train_id: int
    timestamp: float
