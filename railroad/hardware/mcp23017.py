class MCP23017:
    """MCP23017 input backend. GPIO direction/pull-up setup is fail-closed."""
    IODIRA, IODIRB, GPPUA, GPPUB, GPIOA, GPIOB = 0x00, 0x01, 0x0C, 0x0D, 0x12, 0x13
    def __init__(self, address: int, bus=None, enabled: bool = False):
        self.address, self.bus, self.enabled = address, bus, bool(enabled)
        if self.enabled:
            if bus is None: raise RuntimeError("MCP23017 requires an I2C bus")
            bus.write_byte_data(address, self.IODIRA, 0xFF); bus.write_byte_data(address, self.IODIRB, 0xFF)
            bus.write_byte_data(address, self.GPPUA, 0xFF); bus.write_byte_data(address, self.GPPUB, 0xFF)
    def read_inputs(self):
        if not self.enabled or self.bus is None: raise RuntimeError("sensor hardware is disabled")
        return self.bus.read_byte_data(self.address, self.GPIOA) | (self.bus.read_byte_data(self.address, self.GPIOB) << 8)
