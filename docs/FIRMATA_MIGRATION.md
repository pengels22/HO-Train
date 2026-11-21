# USB Firmata controller migration

The Pi controller is being migrated from the former MCP23017/PCA9685 I²C
inventory to two USB Firmata boards:

- Arduino Mega 2560: turnout reed inputs D14–D41, seven motor H-bridge pairs,
  and the farm/town crossing servos on D44/D45.
- Arduino Nano Classic: active-low turnout direction relays D2–D9 and yard
  power relays D10–D12.
- Arduino Nano ESP32: the dedicated IR receiver endpoint map.
- XIAO ESP32-C6 boards: dedicated turntable and rotary tipper controllers;
  their local pin maps and protocols are not routed through Firmata.

## Commissioning state

`config/firmata_layout.yaml` is the authoritative physical map. Firmata is
enabled for the commissioned Mega, while the relay Nano remains optional
until its stable `/dev/serial/by-id/` path is verified on the Pi.
Loading or validating the configuration is side-effect free. The runtime does
not open the old I²C devices when the Firmata block is present.

Install the optional hardware dependencies only on the controller host:

```text
python3 -m pip install -e '.[hardware]'
```

Use a matching StandardFirmata/StandardFirmataPlus-compatible sketch on the
Mega and Nano. Verify board identity, serial path, firmware, and pin wiring
before connecting relay and actuator power. The first connection must be made
with motor, relay, and servo power disconnected. Startup initializes motors
to zero, crossing servos to neutral (90°), and active-low relays HIGH.

## I/O editing

The Settings page edits tags and configuration/status and saves the complete
map to `config/io_config.csv` through `/api/io-config`. It displays Mega
outputs, Mega reed inputs, Nano relay outputs, Nano ESP32 IR channels, and
dedicated XIAO controller status. Turntable and tipper pins are intentionally
not duplicated in the Mega/Nano input pages.

## Retained compatibility

The old I²C modules and YAML entries remain only as migration compatibility
until the rest of the repository is pruned. They are not selected by the
Firmata runtime. Locomotive UDP protocol fields, including the legacy `0x80`
stop flag, remain unchanged pending coordinated firmware migration.

Firmware is not flashed automatically by the runtime. When hardware mode is
explicitly started, the Mega is initialized to zero/neutral outputs; the
relay Nano remains offline-tolerant until connected.

## Lab 1 commissioning record

On 2026-11-21, Lab 1 identified the connected Mega as Arduino VID:PID
`2341:0042`, board `arduino:avr:mega`, with the persistent path recorded in
`config/firmata_layout.yaml`. Firmata library 2.5.9 `StandardFirmataPlus`
compiled and uploaded successfully to that path. The relay Nano was not
connected, and the runtime remains disabled pending full electrical review.
