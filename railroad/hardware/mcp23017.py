class MCP23017:
    """MCP23017 backend for explicitly mapped digital I/O.

    Inputs default to pull-up, while output latches are cleared during setup.
    No output is driven by construction unless a caller explicitly configures
    an output and writes it.
    """
    IODIRA, IODIRB, GPPUA, GPPUB, GPIOA, GPIOB = 0x00, 0x01, 0x0C, 0x0D, 0x12, 0x13
    OLATA, OLATB, IPOLA, IPOLB = 0x14, 0x15, 0x02, 0x03

    def __init__(self, address: int, bus=None, enabled: bool = False,
                 *, input_mask: int = 0xFFFF, pullup_mask: int = 0xFFFF):
        self.address, self.bus, self.enabled = address, bus, bool(enabled)
        if self.enabled:
            if bus is None: raise RuntimeError("MCP23017 requires an I2C bus")
            self.configure(input_mask=input_mask, pullup_mask=pullup_mask)

    def configure(self, *, input_mask: int = 0xFFFF, pullup_mask: int = 0xFFFF):
        if not self.enabled or self.bus is None:
            raise RuntimeError("sensor hardware is disabled")
        for value, register in ((input_mask & 0xFF, self.IODIRA),
                                ((input_mask >> 8) & 0xFF, self.IODIRB),
                                (pullup_mask & 0xFF, self.GPPUA),
                                ((pullup_mask >> 8) & 0xFF, self.GPPUB)):
            self.bus.write_byte_data(self.address, register, value)
        # Clear output latches before any output is selected by the application.
        self.bus.write_byte_data(self.address, self.OLATA, 0)
        self.bus.write_byte_data(self.address, self.OLATB, 0)

    def read_inputs(self):
        if not self.enabled or self.bus is None: raise RuntimeError("sensor hardware is disabled")
        return self.bus.read_byte_data(self.address, self.GPIOA) | (self.bus.read_byte_data(self.address, self.GPIOB) << 8)

    def read_pin(self, pin: int) -> bool:
        if not 0 <= pin < 16:
            raise ValueError("MCP23017 pin must be 0..15")
        return bool(self.read_inputs() & (1 << pin))

    def write_pin(self, pin: int, value: bool) -> None:
        if not self.enabled or self.bus is None:
            raise RuntimeError("sensor hardware is disabled")
        if not 0 <= pin < 16:
            raise ValueError("MCP23017 pin must be 0..15")
        register = self.OLATA if pin < 8 else self.OLATB
        bit = pin if pin < 8 else pin - 8
        current = self.bus.read_byte_data(self.address, register)
        current = (current | (1 << bit)) if value else (current & ~(1 << bit))
        self.bus.write_byte_data(self.address, register, current)
