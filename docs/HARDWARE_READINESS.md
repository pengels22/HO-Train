# Hardware readiness matrix

| Interface | Current status | Source / remaining requirement |
|---|---|---|
| UDP locomotive dispatcher global STOP | Implemented and mocked | `railroad/transport/udp.py`, `railroad/transport/locomotive.py`; the legacy 0x80 stop bit is retained for firmware compatibility; network delivery needs bench verification. |
| Registered USB local STOP/recovery/heartbeat | Implemented boundary and mocked acknowledgements | `railroad/transport/usb.py`; configure stable serial paths and validate controller reply formats; legacy serial commands remain compatible where required. |
| Four M5 Atom locomotive controllers / IR transmitters | Firmware implementation present and preserved | `firmware/locomotive_m5_atom_echo/`; compile four configured IDs against the selected Arduino-ESP32 core and validate IR symbol timing. |
| XIAO turntable DRV8833/relays/switches/reeds | Firmware state machine and pin assignments present | `firmware/turntable_esp32c6/turntable_esp32c6.ino`; compile and bench-test relay polarity, limit switches, and mechanical timeout. |
| XIAO rotary tipper controller | Validated C6 GPIO map implemented; mechanical polarity/limits still require bench verification | `config/tipper.yaml`, `firmware/tipper_esp32c6/tipper_esp32c6.ino`; verify gripper direction, 800 ms travel, feedback polarity, and mechanical limits before arming. |
| Turntable Python lifecycle | Implemented and tested | `railroad/turntable.py`; hardware controller acknowledgement still required before operation. |
| Tipper motor/decoupler | Dedicated C6 firmware fail-closed path present | `railroad/automation/tipper.py`, `firmware/tipper_esp32c6/README.md`; board pin map, feedback polarity, and mechanical limits remain to be verified. |
| Mega/Nano Firmata I/O | Implemented, USB identity and electrical harness still require commissioning | `config/firmata_layout.yaml`, `railroad/hardware/firmata.py`; outputs initialize safe-off/neutral and missing relay Nano is tolerated. |
| Yard relays and turnout SPDT relays | Safety/configuration boundary only | Yard D10-D12 and turnout D2-D9 are active-low Nano Classic Firmata outputs; external turnout +12 V is separate and never sourced by the Pi. The only genuine servos are the Farm/Town gates on Mega D44/D45. |
| USB IR receiver | Production protocol compiled; physical channels unverified | `firmware/ir_receiver_nano_esp32/`, `config/ir_receivers.yaml`, and the registered serial port require deployment/field validation. |

No row is considered hardware-ready until firmware compilation and physical
bench validation succeed.
