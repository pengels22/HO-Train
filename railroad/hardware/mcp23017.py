class MCP23017:
    def __init__(self, address: int, enabled: bool = False): self.address, self.enabled = address, enabled
    def read_inputs(self):
        if not self.enabled: raise RuntimeError("sensor hardware is disabled")
        return 0
