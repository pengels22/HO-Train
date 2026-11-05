class Watchdog:
    def __init__(self, timeout_seconds: float = 3): self.timeout_seconds = timeout_seconds
    def expired(self, elapsed_seconds: float) -> bool: return elapsed_seconds > self.timeout_seconds
