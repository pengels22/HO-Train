class MotorController:
    """Business-level motor boundary; no physical feedback is implied."""
    def command(self, motor_id: int, speed: int) -> None: raise NotImplementedError
