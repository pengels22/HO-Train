# Dispatcher stop protocol

This document describes the current software stop system. The project does
not require or monitor a physical emergency-stop input.

## Dispatcher global STOP

The dispatcher immediately sends a zero-speed broadcast to all locomotives and
keeps repeating it while the dispatcher stop is active. The existing 12-byte
locomotive frame remains:

- `train_id = 0xFF` for all locomotives
- `flags & 0x80` for the legacy broadcast stop flag
- `speed = 0`, `target = 0`
- incrementing sequence number and existing CRC16
- 100 ms repeat interval while latched

The `0x80` flag, firmware state `ESTOP_LATCHED`, and telemetry field `estop`
are retained solely for already-flashed firmware compatibility. They do not
represent a physical emergency-stop system.

Clearing the dispatcher stop stops repetition but leaves motion disarmed. A
separate explicit rearm handshake is required before nonzero motion commands
are accepted. A normal zero-speed command never clears the firmware latch.

## Individual locomotive STOP

An individual STOP sends a zero-speed command for one locomotive through the
same command transport. It does not assert the global broadcast flag and does
not stop unrelated locomotives or accessories.

## Local accessory STOP

Turntable and rotary tipper stops are sent through their registered USB serial
controllers. Tipper routine STOP is non-latching: it turns the rotation motor
and decoupler off, then the controller status is read back to verify both are
off. Older `ESTOP`/`REARM` serial vocabulary remains accepted by tipper
firmware only for compatibility with previously flashed images.

Accessory communication faults remain local and must not become a global
locomotive stop. The turntable and tipper each retain their own interlocks and
recovery procedures.

## Communications watchdogs

Locomotive telemetry freshness is evaluated per locomotive. A moving
locomotive with stale or missing telemetry is unsafe; a parked locomotive may
be powered down on an isolated yard circuit without creating a fault. A
disconnected unrelated accessory or locomotive does not stop the rest of the
fleet.

## Motion authorization and recovery

The Raspberry Pi 4B is the central dispatcher. Every nonzero locomotive
command passes through `LocomotiveCommandTransport`. Startup is disarmed;
recovery is `clear stop`, reconcile active faults/positions, then explicit
`rearm`. No cached throttle is resumed automatically.

## Network and hardware configuration

Locomotive UDP destinations and ports come from `config/locomotives.yaml` and
the declarative controller inventory in `config/hardware.yaml`; this document
does not define a separate broadcast network. Turntable and tipper use their
configured USB serial paths at 115200 baud. Yard relay outputs remain
`UNASSIGNED` and default OFF until an approved physical mapping and writer are
commissioned.
