# Tipper E-Stop interface

The Python dispatcher now accepts an allow-listed `tipper` stop callback and
invokes it independently during every global E-Stop. No tipper controller
firmware or serial protocol exists in this workspace, so no GPIO, relay, or
serial pin is invented here. A validated controller adapter must register its
immediate-stop function with `Dispatcher.attach_accessory_stops(tipper=...)`
before bench operation. Until then simulation remains hardware-silent.

The reserved newline protocol is JSON (`ESTOP`, `STOP`, `STATUS`, and
`REARM` commands with a transaction ID). Controllers should reply with a
matching transaction and explicit `motor:false` / `decoupler:false` fields for
stop acknowledgement. The Python `TipperSerialController` accepts only these
commands and uses an allow-listed, already-registered serial port. The actual
board, port, motor pins, and decoupler command remain deployment configuration.
