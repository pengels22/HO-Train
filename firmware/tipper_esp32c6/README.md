# Dedicated XIAO ESP32-C6 rotary tipper controller

`tipper_esp32c6.ino` is the dedicated XIAO ESP32-C6 accessory firmware. It
starts with motor, lock, and decoupler outputs inactive and requires explicit
serial rearm. It monitors the agreed IR-clear, Hall, and encoder signals and
fails closed on a 500 ms communications watchdog or rotation timeout.

The C6 pin macros intentionally default to `-1`: the owner has not supplied a
verified C6 harness pinout. Provide every `TIPPER_*` macro from the verified
commissioning build; the firmware reports `pin_map_verified:false` and refuses
rearm until then. Raspberry Pi BCM assignments in the master wiring plan remain
Pi-side signals and are not silently reused as C6 GPIO numbers.

The newline protocol is JSON (`ESTOP`, `STOP`, `STATUS`, `REARM`, `LOCK`,
`UNLOCK`, `DECOUPLER OFF`, `ROTATE CW/CCW`, and `HOME`) with a transaction ID.
`ESTOP` remains available as a plain line. Controllers should reply with a
matching transaction and explicit `motor:false` / `decoupler:false` fields for
stop acknowledgement. The Python `TipperSerialController` accepts only these
commands and uses an allow-listed, already-registered serial port. The actual
board, port, and C6 pin macros remain deployment configuration.
