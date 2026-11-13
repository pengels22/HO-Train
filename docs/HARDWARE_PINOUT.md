# Hardware pinout

See `config/` for the agreed provisional assignments. The controller split is:

| Controller | Assignment | Pin status |
|---|---|---|
| Raspberry Pi 4B | Central dispatcher and MCP/PCA railroad I/O; serial interface to the dedicated tipper controller | BCM assignments in `config/hardware.yaml`; verify harness before enabling |
| M5 Atom Echo x4 | Locomotive motor driver, UDP command receiver, watchdog, telemetry, IR transmitter | Existing firmware assignments are preserved; compile/bench-verify each locomotive ID |
| XIAO ESP32-C6 | Dedicated turntable controller | `D0-D7` assignments are in `config/turntable.yaml`; verify board variant/harness |
| XIAO ESP32-C6 | Dedicated rotary tipper controller | No C6 GPIO numbers are assigned until the owner-supplied harness is verified |

The rotary tipper's motor, lock, decoupler, sensors, and encoder belong to the
dedicated XIAO ESP32-C6. No Pi BCM pin is assigned to those functions, and no
Pi output may be wired in parallel with a future C6 assignment. The tipper
firmware uses `TIPPER_*` compile definitions, defaults every one to `-1`,
reports `pin_map_verified:false`, and refuses rearm until a verified C6 pin map
is provided.
