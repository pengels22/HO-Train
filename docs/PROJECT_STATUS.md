# Project status

## Implemented

- Git repository on `main`; simulation-first Python package and configuration layout.
- Four-locomotive models, safe manual takeover, joystick normalization, IR framing/CRC, occupancy sections, route reservation, turnout interlocking, emergency stop, tipper safety skeleton, and local status dashboard.
- Hardware assignment configuration for PCA9685, MCP23017, motors, servos, sensors, IR locations, and safety placeholders.

## Tested

- Core unit tests in `tests/` run without physical hardware.

## Simulated only

- All locomotive motion, sensors, turnouts, tipper sequence, dashboard, and hardware outputs.

## Awaiting hardware

- Raspberry Pi GPIO/I²C validation, exact ESP32 motor driver/pins, IR receiver decoder, surveyed track graph, servo geometry, tipper home/alignment feedback, electrical/fuse verification, and MQTT integration.

## Known issues / remaining tasks

- Expand full event-driven simulator and dashboard controls; add YAML schema validation, real Linux evdev/MQTT adapters, complete tipper transitions, deployment scripts, and hardware-in-loop validation.
