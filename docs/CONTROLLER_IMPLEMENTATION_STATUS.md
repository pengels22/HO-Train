# Dispatcher implementation status

This branch is simulation-first, not commissioned train automation.

## Included
- Four train objects; 15 exclusive operating zones and one train per destination.
- Latched global stop if an expected checkpoint does not arrive on time.
- Freight load and tipper validation; a passenger/freight separation.
- Protected MAIN-3 and UND-1 during tipper operations/faults, without forbidding MAIN-2-to-Mine travel.
- Three switched yard power domains; Stalls 1A and 1B share Track 1.
- Binary UDP command packet encoder/decoder (not enabled in hardware).
- Nano USB IR JSON event parser (not yet connected to serial device).
- Authoritative logical turnout map, 11 IR positions and yard power configuration.

## Work required before live trains
- Actual I/O configuration editor, three-tab web dashboard and exact RailModeller background with centerline coordinates.
- Per-loco speed calibration and train-position interpolation; Hall tail-of-train verification across all cars.
- Arduino Nano 11-channel decoder and actual XIAO firmware integration; verify pulse timing and infrared receiver field of view.
- Hardware drivers for PCA9685, MCP23017, track relay outputs, and USB serial Nano.
- Complete tipper sensor/action state machine and safety qualification, plus bench tests.
- Security and operator interlocks before any hardware outputs are enabled.

## Safety
The connected locomotives must never be commanded to move from simulation endpoints. A missing checkpoint is a GLOBAL stop. Parked, intentionally unpowered locomotives stay reserved. A Hall sensor reading CLEAR between cars cannot prove tail clearance.
