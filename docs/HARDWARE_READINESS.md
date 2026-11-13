# Hardware readiness matrix

| Interface | Current status | Source / remaining requirement |
|---|---|---|
| Raspberry Pi physical E-Stop GPIO | Configurable, not assigned | `config/hardware.yaml`, `railroad/hardware/gpio.py`; validate the approved BCM pin and RPi input at commissioning. |
| UDP locomotive E-Stop | Implemented and tested | `railroad/transport/udp.py`, `railroad/transport/estop.py`; network delivery still requires the approved HO-Railroad Wi-Fi. |
| Registered USB E-Stop/rearm/heartbeat | Implemented boundary and mocked acknowledgements | `railroad/transport/usb.py`; configure stable serial paths and validate controller reply formats. |
| Four M5 Atom locomotive controllers / IR transmitters | Firmware implementation present and preserved | `firmware/locomotive_m5_atom_echo/`; compile four configured IDs against the selected Arduino-ESP32 core and validate IR symbol timing. |
| XIAO turntable DRV8833/relays/switches/reeds | Firmware state machine and pin assignments present | `firmware/locomotive_esp32/turntable_esp32c6.ino`; compile and bench-test relay polarity, limit switches, and mechanical timeout. |
| XIAO rotary tipper controller | Assignment and serial safety boundary present; firmware not yet implemented | `config/hardware.yaml`, `firmware/tipper_controller/README.md`; define the board firmware, feedback schema, and validated pins before arming. |
| Turntable Python lifecycle | Implemented and tested | `railroad/turntable.py`; hardware controller acknowledgement still required before operation. |
| Tipper motor/decoupler | Safe abstract and serial protocol boundary | `railroad/automation/tipper.py`, `firmware/tipper_controller/README.md`; board, port, feedback schema, and pin assignments remain undefined. |
| PCA9685 motor/servo outputs | Existing configurable interface, not commissioned here | `config/hardware.yaml` and hardware modules; no outputs are initialized in simulation. |
| MCP23017 sensor inputs | Existing configuration, not commissioned here | `config/hardware.yaml`, `config/sensors.yaml`; validate addresses and duplicate assignments on the Pi. |
| Yard relays and turnout servos | Safety/configuration boundary only | Hardware output mapping and commissioning remain required; simulation keeps them disabled. |
| USB IR receivers | Protocol/configuration boundary | Registered receiver ports and validated serial framing remain deployment configuration. |

No row is considered hardware-ready until firmware compilation and physical
bench validation succeed.
