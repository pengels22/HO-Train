# Configuration sources

Hardware design defaults are documented in `docs/HARDWARE_PINOUT.md`, with allocations declared in `config/hardware.yaml`, `config/servos.yaml`, `config/motors.yaml`, `config/ir_receivers.yaml`, `config/tipper.yaml` and `config/turntable.yaml`.

The user-editable I/O settings are the effective runtime mapping after validation and persistence; nominal defaults must not prevent valid reassignments. Hardware verification is separate from configuration. The Nano ESP32 owns station IR inputs; MCP23017 GPB2–GPB4 at address 0x21 are currently spare. Turnouts A–H are all part of the design; turnout H uses PCA9685 0x42 CH13. Yard power relay pins are not allocated.

The imported unified geography is the current geography reference; simulation/test data must not override real hardware configuration. Passive splitters are not commanded turnout I/O.
