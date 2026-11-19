# Authoritative I/O configuration

The web Settings UI must list **all assignable channels**, whether currently occupied or spare, from the Pi, MCP23017 0x20/0x21, PCA9685 0x40/0x41/0x42 and applicable USB devices. Show board address/physical pin, function, location, direction, polarity, configured/actual status and verification status; permit filtering, editing, validation and persistent save. Reject duplicate/conflicting allocations and incompatible pin capabilities. Saving metadata must not energize outputs.

The configuration pipeline uses `config/io_config.csv` (where supported) and `/api/io-config` for the dashboard. The complete inventory, including USB-based controllers, must be reconciled with the physical board implementations. Existing UI limitations are implementation gaps, not restrictions on owner-confirmed assignability.

Current design: Nano ESP32 production IR owns the station receivers, MCP23017 0x21 GPB2–GPB7 are spare, turnout H exists on PCA9685 0x42 CH13, yard relay channels remain unassigned, and direct Pi accessory GPIO remains unassigned. See `docs/HARDWARE_PINOUT.md`.

Do not conflate channel assignment confirmation with physical hardware verification. Board-local safety and electrical limits remain mandatory for any permitted reassignment.
