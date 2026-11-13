# Hardware readiness matrix

| Interface | Current status | Source / remaining requirement |
|---|---|---|
| Raspberry Pi physical E-Stop GPIO | Not installed or assigned | Stop propagation uses the dispatcher and controller-local watchdog/E-Stop protocols. |
| UDP locomotive E-Stop | Implemented and tested | `railroad/transport/udp.py`, `railroad/transport/estop.py`; network delivery still requires the approved HO-Railroad Wi-Fi. |
| Registered USB E-Stop/rearm/heartbeat | Implemented boundary and mocked acknowledgements | `railroad/transport/usb.py`; configure stable serial paths and validate controller reply formats. |
| Four M5 Atom locomotive controllers / IR transmitters | Firmware implementation present and preserved | `firmware/locomotive_m5_atom_echo/`; compile four configured IDs against the selected Arduino-ESP32 core and validate IR symbol timing. |
| XIAO turntable DRV8833/relays/switches/reeds | Firmware state machine and pin assignments present | `firmware/turntable_esp32c6/turntable_esp32c6.ino`; compile and bench-test relay polarity, limit switches, and mechanical timeout. |
| XIAO rotary tipper controller | Validated C6 GPIO map implemented; mechanical polarity/limits still require bench verification | `config/tipper.yaml`, `firmware/tipper_esp32c6/tipper_esp32c6.ino`; verify gripper direction, 800 ms travel, feedback polarity, and mechanical limits before arming. |
| Turntable Python lifecycle | Implemented and tested | `railroad/turntable.py`; hardware controller acknowledgement still required before operation. |
| Tipper motor/decoupler | Dedicated C6 firmware fail-closed path present | `railroad/automation/tipper.py`, `firmware/tipper_esp32c6/README.md`; board pin map, feedback polarity, and mechanical limits remain to be verified. |
| PCA9685 motor/servo outputs | Existing configurable interface, not commissioned here | `config/hardware.yaml` and hardware modules; no outputs are initialized in simulation. |
| MCP23017 sensor inputs | Existing configuration, not commissioned here | `config/hardware.yaml`, `config/sensors.yaml`; validate addresses and duplicate assignments on the Pi. |
| Yard relays and turnout servos | Safety/configuration boundary only | Hardware output mapping and commissioning remain required; simulation keeps them disabled. |
| USB IR receivers | Protocol/configuration boundary | Registered receiver ports and validated serial framing remain deployment configuration. |

No row is considered hardware-ready until firmware compilation and physical
bench validation succeed.
