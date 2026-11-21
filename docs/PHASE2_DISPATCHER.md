# Phase 2 dispatcher boundary

The dispatcher separates route planning from hardware actuation. A
`RoutePlan` contains the train, origin, destination, zones, turnout positions,
expected checkpoints, required controllers, status, and blocking reason.

Routes are conservative by default: the current layout configuration is marked
physically unverified, so a hardware runtime cannot start a movement from a
route plan until the surveyed topology, controller availability, occupancy,
and commanded turnout alignment are all present. Turnouts A-G are relay-driven
three-wire SPDT loads with logically assigned common/straight/divergent reed
inputs. Those inputs are not yet physically validated; until validation the
dispatcher records the relay command as an open-loop assumption and must not
describe it as sensor-confirmed. No missing sensor or controller is interpreted
as clear.

The automatic controls are explicit. `enable_automatic` enables scheduling but
does not start a cycle; `run_cycle_once` is the operator authorization for one
eligible cycle. `manual_takeover` cancels automatic control for one locomotive
and issues its individual stop. Pending destination requests can be submitted
or cancelled independently.

The Pi I/O inventory is the USB Firmata Mega/Nano layout in
`config/firmata_layout.yaml`, plus the USB Nano ESP32 IR decoder and dedicated
XIAO controllers. Turntable and tipper I/O are local to those C6 boards. A
missing relay Nano, IR decoder, or accessory controller is reported as
unavailable and must not stop unrelated locomotive operation. Firmata outputs
initialize safe-off/neutral and require reconciliation before being considered
ready.

The logical 0x41 output order is turnout A-G on channels 0-6, spare channels
7-13, and Farm/Town gate servos on channels 14-15. MCP inputs are grouped as
common/straight/divergent reed inputs for each turnout, followed by the
station inputs.

Topology, physical relay/turnout commissioning, Nano IR checkpoint assignments, consist-clearance
signals, yard relay mappings, and calibrated locomotive speeds remain physical
commissioning requirements. Until verified, affected automatic routes remain
blocked; no firmware is flashed and no physical outputs are energized by the
software tests.
