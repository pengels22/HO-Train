# Phase 2 dispatcher boundary

The dispatcher separates route planning from hardware actuation. A
`RoutePlan` contains the train, origin, destination, zones, turnout positions,
expected checkpoints, required controllers, status, and blocking reason.

Routes are conservative by default: the current layout configuration is marked
physically unverified, so a hardware runtime cannot start a movement from a
route plan until the surveyed topology, controller availability, occupancy,
and physical turnout feedback are all present. No missing sensor or controller
is interpreted as clear or aligned.

The automatic controls are explicit. `enable_automatic` enables scheduling but
does not start a cycle; `run_cycle_once` is the operator authorization for one
eligible cycle. `manual_takeover` cancels automatic control for one locomotive
and issues its individual stop. Pending destination requests can be submitted
or cancelled independently.

The Pi I/O inventory remains exactly two PCA9685 boards (`0x40` motors and
`0x41` servos), two MCP23017 input boards (`0x20` and `0x21`), and the USB
controllers. I²C boards are probed independently. An absent board is reported
as `UNAVAILABLE`, retried periodically, and cannot stop unrelated controller
operation. Newly connected PWM boards initialize safe-off and require
reconciliation before being considered ready.

Topology, turnout feedback, Nano IR checkpoint assignments, consist-clearance
signals, yard relay mappings, and calibrated locomotive speeds remain physical
commissioning requirements. Until verified, affected automatic routes remain
blocked; no firmware is flashed and no physical outputs are energized by the
software tests.
