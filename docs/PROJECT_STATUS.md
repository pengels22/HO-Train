# Project status

## Implemented

- Hardware-first Raspberry Pi 4B control package with simulation retained as the safe developer default.
- Four-locomotive models, safe manual takeover, joystick normalization, IR framing/CRC, occupancy sections, route reservation, turnout interlocking, emergency stop, tipper safety skeleton, and local status dashboard.
- Hardware assignment configuration for PCA9685, MCP23017, motors, servos, sensors, IR locations, and safety placeholders.
- Validated 32-entry MCP23017 registry (25 proposed inputs plus 7 spares), corrected A-G mapping, optional Pi I2C/PCA/DRV backends, stable reed edge events, and guarded three-section yard output model.
- Pass 2 branch: 15-zone model, configurable normalized boundary polygons, zone reservation/occupancy engine, locomotive zone fields, preserved layout image, and proposed SVG overlay/dashboard view.

## Tested

- Core unit tests in `tests/` run without physical hardware.

## Bench/unverified

- Physical locomotive motion, sensor electrical levels, turnouts, tipper sequence, and relay harness remain bench-unverified. Drivers fail closed and require explicit hardware enable/arm.
- All zone geometry, zone transitions, and multi-zone route conflict behavior.

## Awaiting hardware

- Raspberry Pi GPIO/I²C electrical validation, exact XIAO ESP32-C6/DRV8871 firmware pinout and build, IR decoder, surveyed track graph, servo geometry, tipper home/alignment feedback, electrical/fuse verification, and MQTT integration.
- Physical survey/confirmation of the 15 zone boundaries, elevations, segment connectivity, turnout adjacency, and consist-clearance behavior.

## Known issues / remaining tasks

- Expand full event-driven simulator and dashboard controls; add YAML schema validation, real Linux evdev/MQTT adapters, complete tipper transitions, deployment scripts, and hardware-in-loop validation.
- Supply/verify RailModeller topology and promote proposed polygons only after review; add editor save/reload workflow and two-train zone simulator scenarios.
