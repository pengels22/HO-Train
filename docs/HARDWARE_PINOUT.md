# Hardware configurations — active pinout baseline v1.1

The owner-confirmed design below supersedes historical pinouts. Actual harness commissioning is tracked separately from design confirmation. All assignable I/O functions must be changeable in web Settings with conflict validation, persistence and live status. No direct Pi GPIO accessory outputs are assigned.

## Standard Raspberry Pi 4B I2C header

| Physical pin | Pi function | Standard harness connection |
|---|---|---|
| 1 | 3.3 V | Low-voltage/reference side of bidirectional level shifter |
| 3 | BCM2 / SDA1 | SDA on low-voltage side of level shifter |
| 4 | 5 V | 5 V supply |
| 5 | BCM3 / SCL1 | SCL on low-voltage side of level shifter |
| 6 | Ground | Common ground |

Check downstream board voltage requirements and shifter/pull-up arrangement before applying power. This is the standard five-signal header, not a fixed keyed connector orientation.

## I2C controller addresses

- PCA9685 0x40: CH0/1 mine lift; 2/3 ski chairlift; 4/5 grain auger; 6/7 farm road; 8/9 ski lodge road; 10/11 long road; 12/13 town road; 14/15 spare.
- PCA9685 0x41: CH0–15 spare.
- PCA9685 0x42: CH0 farm gates, CH1 turnout A, CH2 B, CH3 C, CH4 town gates, CH5 yard servo 1, CH6 yard servo 2, CH7 yard servo 3, CH8 spare, CH9 turnout D, CH10 E, CH11 F, CH12 G, **CH13 turnout H (owner confirmed)**, CH14/15 spare.
- MCP23017 0x20: GPA0/1/2 turnout A; GPA3/4/5 B; GPA6/GPA7/GPB0 C; GPB1/2/3 D; GPB4/5/6 E; GPB7 spare.
- MCP23017 0x21: GPA0/1/2 turnout F; GPA3/4/5 G; GPA6 mine location, GPA7 farm location, GPB0 ski location, GPB1 town location; GPB2–GPB7 spare. **Station IR signals do not use MCP.** These GPIO allocations are current defaults and can be reassigned in the web UI.

## USB controllers and locomotive interfaces

| Controller | Pin(s) | Function |
|---|---|---|
| M5 Atom Echo locomotive | GPIO19, GPIO22, GPIO23 | Motor forward PWM, reverse PWM, IR transmitter |
| XIAO ESP32-C6 locomotive alternative | D7/GPIO17, D8/GPIO19, D9/GPIO20 | Motor forward PWM, reverse PWM, IR transmitter |
| XIAO ESP32-C6 turntable | D0–D7 | Home, rotated switch, rotation IN1, rotation IN2, polarity relay, track power relay, reed A, reed B, respectively |
| XIAO ESP32-C6 rotary tipper | D2/GPIO2, D3/GPIO21, D4/GPIO22, D5/GPIO23 | Hall front, Hall rear, Hall clear, encoder |
| XIAO ESP32-C6 rotary tipper | D6/GPIO16, D7/GPIO17, D8/GPIO19, D9/GPIO20, D10/GPIO18 | Rotation IN1/IN2, gripper IN3/IN4, active-low decoupler |
| Nano ESP32 production IR | D2–D12 | Existing eleven confirmed location-receiver inputs; station receivers also belong to this controller; *additional physical input assignments remain to be specified* |
| Classic Arduino Nano dual throttle | D2/D3, D4/D5, D6/D7 | Left turnout left/right, right turnout left/right, left/right thumb-enable |
| Classic Arduino Nano dual throttle | A0, A1 | Left/right throttle potentiometers |
| Classic Arduino Nano dual throttle | D13/D11, D10/D9/D8, A4/A5 | LCD SCK/MOSI, CS/DC/RST, touch SDA/SCL |

The classic Nano dual-throttle mapping above is owner-confirmed. An alternative development sketch on the HID_Dev branch uses a different Nano ESP32 mapping and **does not override** this decision. LCD controller and touch electrical characteristics still require verification against the actual module.

The Nano ESP32 single-input bench device will be repurposed as the production IR controller. Eleven D2–D12 locations are confirmed; do not invent a three-station pin extension without an input-count and bus/USB architecture decision. Existing bench firmware is not yet a validated production multi-input decoder.

## Yard power and STOP

Three physical yard tracks: Track 1 shares power for stalls 1A/1B; Track 2 and Track 3 separately. Relay output pin assignments are deliberately **pending**. No dedicated physical E-stop hardware or GPIO exists in the project. Dispatcher STOP, local controller STOP, communication watchdogs and operational interlocks remain.

## Commissioning

Owner-confirmed mapping does not equal electrical harness verification. Confirm pin polarity, sensor voltage, physical wiring, bus scan and functional response before connecting powered actuators. The web Settings mapping must remain editable, validate conflicts and persist changes.
