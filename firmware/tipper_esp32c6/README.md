# Dedicated XIAO ESP32-C6 rotary tipper controller

`tipper_esp32c6.ino` is the dedicated XIAO ESP32-C6 accessory firmware. It
uses the validated GPIO map in `config/tipper.yaml`: GPIO16/17 for rotation,
GPIO19/20 for the gripper motor, GPIO18 for the decoupler, GPIO2/21/22 for
Hall sensors, and GPIO23 for the encoder. Forward gripper motion unlocks and
reverse motion locks for 800 ms. All actuator outputs start LOW and require
explicit serial rearm; the 500 ms communications watchdog stops every output.

The C6 pin macros match the supplied board-level harness table. IR front/back
inputs remain optional because no C6 GPIOs were assigned to them in that table.
The firmware reports `pin_map_verified:true` when the assigned motor, gripper,
decoupler, Hall, and encoder pins are compiled in.

The newline protocol is JSON (`ESTOP`, `STOP`, `STATUS`, `REARM`, `LOCK`,
`UNLOCK`, `DECOUPLER OFF`, `ROTATE CW/CCW`, and `HOME`) with a transaction ID.
`ESTOP` remains available as a plain line. Controllers should reply with a
matching transaction and explicit `motor:false` / `decoupler:false` fields for
stop acknowledgement. The Python `TipperSerialController` accepts only these
commands and uses an allow-listed, already-registered serial port. The actual
board, port, and C6 pin macros remain deployment configuration.
