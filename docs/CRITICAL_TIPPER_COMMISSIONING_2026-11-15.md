# Critical tipper control changes (2026-11-15)

## Hardware authority

The dedicated Seeed XIAO ESP32-C6 exclusively controls the rotary tipper:
- D2 / GPIO2: Hall Front, active low
- D3 / GPIO21: Hall Back, active low
- D4 / GPIO22: Hall Clear, active low
- D5 / GPIO23: 40-slot optical encoder (wheel diameter 1.125 in)
- D6 / GPIO16 and D7 / GPIO17: rotation motor
- D8 / GPIO19 and D9 / GPIO20: gripper/lock motor
- **D10 / GPIO18: magnetic decoupler relay**
- D0/GPIO0 and D1/GPIO1 are unassigned.

No train-clearance IR inputs exist on this board. Locomotive destination IR is a
separate tracking system. The encoder optical sensor is solely rotation feedback.

Pi PCA9685 CH14/15 (motor board 0x40) and CH8 (servo board 0x42) are now
unassigned: do not connect these outputs to the tipper.

## Fail-closed commissioning

**Not ready for physical tipper rotation.** `TIPPER_ROTATION_COUNTS_PER_120_DEG`
defaults to zero. Verify how the 1.125-inch encoder wheel is mechanically coupled
to the tipper, measure actual 120-degree travel, set the encoder pulse target,
and validate encoder stall/timeout behavior without a train. One rising-edge
count corresponds to one slot (40 ticks / encoder-wheel revolution).

**Not ready to energize the decoupler.** The firmware default
`TIPPER_DECOUPLER_RELAY_VERIFIED=0` rejects `DECOUPLER ON`. Confirm relay
module input polarity, its voltage/current drive and external suppression;
then set `TIPPER_DECOUPLER_ACTIVE_HIGH` correctly and explicitly opt in.
The coil must be supplied by a separate fused supply; GPIO18 is a *logic*
signal, not a coil power source. ON is a fixed 250 ms pulse; OFF and ESTOP
immediately de-energize it.

**Angular HOME is inhibited.** The Hall Clear sensor detects railroad cars,
not the barrel's angular home. Fit/verify a true mechanical angular reference
or calibrate a protected encoder-based return before enabling HOME.

Rotation checks Hall Front, Hall Back and Hall Clear active-low initially,
the lock state, encoder calibration and decoupler OFF. Firmware state only
reflects commanded lock movement; actual lock-engagement confirmation still
needs commissioning. The dispatcher remains responsible for zone reservations
and consist-count verification.

## Independent failure recovery

Global locomotive rearm no longer calls `ControllerRegistry.rearm_all()`.
A disconnected or locally faulted USB tipper/turntable must not immobilize
healthy locomotives. Accessories retain their own independent safety latches;
local rearm remains an explicit separate operation. Emergency STOP still
fans out to both locomotives and registered accessories, best effort, and
requires confirmation of each unit's actual state before its operation.

## Deployment

This branch is **source only**. No firmware was flashed, no Lab 1 service
configuration was changed, and no physical outputs were energized. Run the
unit tests, compile for Seeed XIAO ESP32-C6, reconcile branch drift from
main, and bench-verify wiring before a planned Lab 1 deployment.
