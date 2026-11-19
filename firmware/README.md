# HO Railroad controller firmware inventory

Firmware presence is not evidence of a commissioned device. Current owner-confirmed assignments are in [Hardware pinout](../docs/HARDWARE_PINOUT.md). Configured GPIO mappings remain editable through the web UI.

| Controller | Firmware | Role |
|---|---|---|
| Raspberry Pi 4B | `railroad/` | USB peripheral dispatcher, I2C outputs/inputs; standard 5-signal 3.3V/5V level-shifted I2C harness |
| M5 Atom Echo | `locomotive_m5_atom_echo/` | Primary locomotive hardware option: GPIO19/22 motor, GPIO23 IR |
| XIAO ESP32-C6 locomotive | `locomotive_xiao_esp32c6/` | Second supported locomotive hardware option: D7/D8 motor and D9 IR |
| XIAO ESP32-C6 tipper | `tipper_esp32c6/` | Dedicated USB tipper including rotation, gripper, Hall, encoder and decoupler |
| XIAO ESP32-C6 turntable | `turntable_esp32c6/` | Dedicated USB turntable, reeds, alignment, polarity and track power |
| Nano ESP32 production IR | `ir_receiver_nano_esp32_bench/` | Existing single-receiver bench firmware to be expanded for production IR receiver system. Eleven location receiver inputs D2–D12 are owner confirmed; extra station inputs still need explicit pin assignment and firmware support |
| Classic Nano dual-throttle | `dual_throttle_nano/` on HID_Dev | Owner-confirmed pinout; firmware integration not yet implemented by Codex |

The separate `ir_receiver/` 11-channel diagnostic and alternate `hid_dual_throttle_nano_esp32/` first-pass UI sketch are development artifacts, **not competing authoritative production pinouts**.

PCA9685 0x40 controls the seven accessory motors (CH0–13), while CH14/15 are spare. PCA9685 0x42 CH13 controls turnout H. MCP23017 station IR assignments are not used. Yard relay output mappings are intentionally deferred.

Preserve no-power-on-start, local watchdogs, dispatcher STOP, motor limits and fault interlocks. Verify physical harness/polarity/IR decoding against the actual installed devices before operation.
