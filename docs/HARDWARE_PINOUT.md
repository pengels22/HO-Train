# Hardware pinout

See `config/` for the agreed provisional assignments. The controller split is:

## Dispatcher and controller STOP

No dedicated physical emergency-stop input is part of the railroad. The Pi
propagates dispatcher STOP to registered locomotive controllers. The USB accessory
controllers provide independent local STOP and communications watchdogs. See
`docs/DISPATCHER_STOP_PROTOCOL.md` for retained legacy wire fields.

| Controller | Assignment | Pin status |
|---|---|---|
| Raspberry Pi 4B | Central dispatcher and MCP/PCA railroad I/O; serial interface to the dedicated tipper controller | BCM assignments in `config/hardware.yaml`; verify harness before enabling |
| M5 Atom Echo x4 | Locomotive motor driver, UDP command receiver, watchdog, telemetry, IR transmitter | Existing firmware assignments are preserved; compile/bench-verify each locomotive ID |
| XIAO ESP32-C6 locomotive bench variant | Locomotive motor driver, UDP command receiver, watchdog, telemetry, IR transmitter | D7/GPIO17 motor IN1, D8/GPIO19 motor IN2, D9/GPIO20 IR; optional target only, never the tipper harness |
| XIAO ESP32-C6 | Dedicated turntable controller | `D0-D7` assignments are in `config/turntable.yaml`; verify board variant/harness |
| XIAO ESP32-C6 | Dedicated rotary tipper controller | GPIO2/21/22 Hall, GPIO23 encoder, GPIO16/17 rotation motor, GPIO19/20 gripper motor, GPIO18 decoupler; verify harness |

The rotary tipper's motor, lock, decoupler, sensors, and encoder belong to the
dedicated XIAO ESP32-C6. No Pi BCM pin is assigned to those functions, and no
Pi output may be wired in parallel with the C6 assignment. The gripper motor
uses GPIO19/20 (IN3/IN4), forward unlock and reverse lock, with an 800 ms
pulse. IR front/back inputs remain unassigned because they are not present in
the supplied C6 table.

### MCP23017 destination IR inputs

The next available MCP inputs are assigned to the missing destination station
receivers. All are active-low inputs; this changes input allocation only and
does not enable any output:

| Board | Input | Function |
|---|---|---|
| MCP23017 `0x21` | GPB4 | Mine station IR |
| MCP23017 `0x21` | GPB2 | Farm station IR |
| MCP23017 `0x21` | GPB3 | Town station IR |

The remaining open inputs are `0x20` GPB7 and `0x21` GPB5–GPB7. Turntable arrival remains
validated by its dedicated C6 alignment/reed feedback.
