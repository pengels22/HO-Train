# Current hardware pinout

The authoritative runtime assignments are in config/firmata_layout.yaml, config/ir_receivers.yaml, config/turntable.yaml and config/tipper.yaml. No MCP23017/PCA9685 board is active.

## Mega 2560 (USB Firmata)

| Function | Pins |
|---|---|
| M2 chairlift PWM | D2/D3 |
| M4 farm road PWM | D4/D5 |
| M5 ski road PWM | D6/D7 |
| M6 long road PWM | D8/D9 |
| M7 town road PWM | D10/D11 |
| Turnout A-H reeds, common/straight/divergent | D14-D37, groups of three |
| Mine/farm/ski/town reeds | D38/D39/D40/D41 |
| Farm/town crossing servos | D44/D45 |
| M1 mine lift digital | D46/D47 |
| M3 grain auger digital | D48/D49 |
| Reserved serial | D0/D1 |
| Spare | D12/D13, D42/D43, D50-D53, A0-A15 |

All reeds active-low pull-up. All seven motors use DRV8833. PWM normalized to 0..1 at Firmata interface. Reed sensors detect train magnets, not point positions.

## Nano Classic (USB Firmata)

D2-D9 turnout A-H; D10-D12 yard tracks 1-3; D13 spare. Twelve installed
relay channels, eleven assigned. Relay outputs are active-low: HIGH is idle and
LOW selects the relay. External pull-ups are fitted. Turnout NC is straight and
NO is divergent; yard relays use NO for switched power. Nano USB path pending.

## Dedicated controllers

Nano ESP32 production IR decoder: fourteen configured receive-only channels on
D2-D12 and A0-A2, matching `config/ir_receivers.yaml`; physical receiver
harness and voltage compatibility remain commissioning items. The one-channel
bench sketch is retained separately for test-track use. Turntable C6 D0/D1
endpoint reeds, D2/D3 motor, D4 polarity relay, D5 track relay, D6/D7 train
reeds. Tipper C6 GPIO16/17 rotation, 19/20 lock, 18 decoupler, 21/2/22 Hall
back/front/clear, 23 encoder. Front/back IR remains unassigned.

Both locomotive variants supported; see their firmware for actual pin maps. No physical E-stop hardware requirement.
