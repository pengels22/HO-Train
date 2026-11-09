# Tipper E-Stop interface

The Python dispatcher now accepts an allow-listed `tipper` stop callback and
invokes it independently during every global E-Stop. No tipper controller
firmware or serial protocol exists in this workspace, so no GPIO, relay, or
serial pin is invented here. A validated controller adapter must register its
immediate-stop function with `Dispatcher.attach_accessory_stops(tipper=...)`
before bench operation. Until then simulation remains hardware-silent.

The reserved newline protocol is `ESTOP`, `STOP`, `STATUS`, and `REARM`, each
terminated by `\n`; controllers should reply with `OK ...`, `ERR ...`, or a
JSON `STATUS` line. The Python `TipperSerialController` accepts only these
commands and uses an allow-listed, already-registered serial port. The actual
board, port, motor pins, and decoupler command remain deployment configuration.
