# Wiring references

The master wiring PDF `HO_Railroad_Complete_Wiring_and_Pinout.pdf` is preserved as an archival design drawing. **Do not use its historical pin assignments for installation.** The active authoritative reference is [Hardware configurations](../HARDWARE_PINOUT.md), including the Raspberry Pi standard I2C header.

The owner-confirmed controller design includes all turnouts A–H (H servo on PCA9685 0x42 CH13), all station IR inputs on the production Nano ESP32 (never MCP23017), and three yard track relays whose pins remain unassigned.

Any prior wiring illustration disagreeing with the current pinout must be revised before field wiring. Physical commissioning is distinct from confirmed design intent.
