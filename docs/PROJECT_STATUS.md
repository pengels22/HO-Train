# Project status

## Implemented

- Hardware-first Raspberry Pi 4B control package with simulation retained as the safe developer default.
- Four-locomotive models, safe manual takeover, joystick normalization, IR framing/CRC, occupancy sections, route reservation, turnout interlocking, dispatcher global STOP and individual locomotive STOP, tipper safety skeleton, and local status dashboard.
- Declarative Firmata layout for the Arduino Mega 2560, Nano Classic relay
  controller, Nano ESP32 IR receiver, and dedicated XIAO accessory boards.
- Validated Mega/Nano USB registry, 28 stable reed input channels, active-low
  turnout/yard relay mapping, safe startup initialization, and guarded
  three-section yard output model. Dedicated legacy I²C drivers have been removed.
- Pass 2 branch: 15-zone model, configurable normalized boundary polygons, zone reservation/occupancy engine, locomotive zone fields, preserved layout image, and proposed SVG overlay/dashboard view.

## Tested

- Core unit tests in `tests/` run without physical hardware.

## Bench/unverified

- Physical locomotive motion, sensor electrical levels, relay-driven turnouts, turnout reed installation, tipper sequence, and relay harness remain bench-unverified. Drivers fail closed and require explicit hardware enable/arm. Turnout state remains commanded open-loop; common/straight/divergent reeds detect trains, not point position; the Farm/Town gates are the only genuine servos.
- All zone geometry, zone transitions, and multi-zone route conflict behavior.

## Awaiting hardware

- Nano Classic USB identity (Mega StandardFirmataPlus was flashed and its path recorded on Lab 1), Mega/Nano electrical
  validation, IR decoder commissioning, surveyed track graph, gate servo
  geometry, tipper home/alignment feedback, electrical/fuse verification, and
  MQTT integration.
- Physical survey/confirmation of the 15 zone boundaries, elevations, segment connectivity, turnout adjacency, and consist-clearance behavior.

## Known issues / remaining tasks

- Expand full event-driven simulator and dashboard controls; add YAML schema validation, real Linux evdev/MQTT adapters, complete tipper transitions, deployment scripts, and hardware-in-loop validation.
- Supply/verify RailModeller topology and promote proposed polygons only after review; add editor save/reload workflow and two-train zone simulator scenarios.
