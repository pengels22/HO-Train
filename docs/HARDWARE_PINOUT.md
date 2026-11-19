# Hardware configurations — complete device pinout baseline v1.2

Owner-confirmed default allocations, **not proof of physical wiring**. All assignable channels must be editable and persist through web Settings, with uniqueness, compatibility and polarity validation. Accessories use USB; only locomotives use wireless. No physical emergency-stop GPIO. Yard relay output pins deferred.

## Raspberry Pi 4B — standard I²C header

| Physical pin | BCM / signal | Purpose |
|---|---|---|
| 1 | 3.3 V | Level shifter low-voltage reference |
| 3 | BCM2 SDA1 | Low-voltage I²C data |
| 4 | 5 V | 5 V supply |
| 5 | BCM3 SCL1 | Low-voltage I²C clock |
| 6 | GND | Common ground |

I²C bus 1. Use an appropriate bidirectional level shifter and suitable pull-ups for attached boards. Other Pi accessory GPIO pins are unassigned.

## PCA9685 motor controller 0x40 — all 16 channels

| Channel | Direction | Default function |
|---|---|---|
| 0 | PWM output | M1 Mine ore lift A |
| 1 | PWM output | M1 Mine ore lift B |
| 2 | PWM output | M2 Ski chairlift A |
| 3 | PWM output | M2 Ski chairlift B |
| 4 | PWM output | M3 Grain auger A |
| 5 | PWM output | M3 Grain auger B |
| 6 | PWM output | M4 Farm road A |
| 7 | PWM output | M4 Farm road B |
| 8 | PWM output | M5 Ski lodge road A |
| 9 | PWM output | M5 Ski lodge road B |
| 10 | PWM output | M6 Long-haul road A |
| 11 | PWM output | M6 Long-haul road B |
| 12 | PWM output | M7 Town road A |
| 13 | PWM output | M7 Town road B |
| 14 | PWM output | Spare |
| 15 | PWM output | Spare |

Motor driver circuitry is required; PCA9685 pins do not directly power motors. CH14/15 spare; tipper motor is on dedicated XIAO.

## PCA9685 expansion controller 0x41 — all 16 channels

| Channel | Direction | Default function |
|---|---|---|
| 0 | PWM output | Spare / unassigned |
| 1 | PWM output | Spare / unassigned |
| 2 | PWM output | Spare / unassigned |
| 3 | PWM output | Spare / unassigned |
| 4 | PWM output | Spare / unassigned |
| 5 | PWM output | Spare / unassigned |
| 6 | PWM output | Spare / unassigned |
| 7 | PWM output | Spare / unassigned |
| 8 | PWM output | Spare / unassigned |
| 9 | PWM output | Spare / unassigned |
| 10 | PWM output | Spare / unassigned |
| 11 | PWM output | Spare / unassigned |
| 12 | PWM output | Spare / unassigned |
| 13 | PWM output | Spare / unassigned |
| 14 | PWM output | Spare / unassigned |
| 15 | PWM output | Spare / unassigned |

## PCA9685 servo controller 0x42 — all 16 channels

| Channel | Direction | Default function |
|---|---|---|
| 0 | PWM output | Farm gates |
| 1 | PWM output | Turnout A |
| 2 | PWM output | Turnout B |
| 3 | PWM output | Turnout C |
| 4 | PWM output | Town gates |
| 5 | PWM output | Yard servo 1 |
| 6 | PWM output | Yard servo 2 |
| 7 | PWM output | Yard servo 3 |
| 8 | PWM output | Spare |
| 9 | PWM output | Turnout D |
| 10 | PWM output | Turnout E |
| 11 | PWM output | Turnout F |
| 12 | PWM output | Turnout G |
| 13 | PWM output | Turnout H |
| 14 | PWM output | Spare |
| 15 | PWM output | Spare |

Turnout H on CH13 is confirmed. CH8 spare; tipper lock is XIAO-owned. Servo V+ requires suitable separate supply.

## MCP23017 0x20 — all 16 input pins

| Pin | Direction | Default function | Polarity |
|---|---|---|---|
| GPA0 | Digital input | Turnout A 1 | Active-low default |
| GPA1 | Digital input | Turnout A 2 | Active-low default |
| GPA2 | Digital input | Turnout A 3 | Active-low default |
| GPA3 | Digital input | Turnout B 1 | Active-low default |
| GPA4 | Digital input | Turnout B 2 | Active-low default |
| GPA5 | Digital input | Turnout B 3 | Active-low default |
| GPA6 | Digital input | Turnout C 1 | Active-low default |
| GPA7 | Digital input | Turnout C 2 | Active-low default |
| GPB0 | Digital input | Turnout C 3 | Active-low default |
| GPB1 | Digital input | Turnout D 1 | Active-low default |
| GPB2 | Digital input | Turnout D 2 | Active-low default |
| GPB3 | Digital input | Turnout D 3 | Active-low default |
| GPB4 | Digital input | Turnout E 1 | Active-low default |
| GPB5 | Digital input | Turnout E 2 | Active-low default |
| GPB6 | Digital input | Turnout E 3 | Active-low default |
| GPB7 | Digital input | Spare | Active-low default |

## MCP23017 0x21 — all 16 input pins

| Pin | Direction | Default function | Polarity |
|---|---|---|---|
| GPA0 | Digital input | Turnout F 1 | Active-low default |
| GPA1 | Digital input | Turnout F 2 | Active-low default |
| GPA2 | Digital input | Turnout F 3 | Active-low default |
| GPA3 | Digital input | Turnout G 1 | Active-low default |
| GPA4 | Digital input | Turnout G 2 | Active-low default |
| GPA5 | Digital input | Turnout G 3 | Active-low default |
| GPA6 | Digital input | Mine location | Active-low default |
| GPA7 | Digital input | Farm location | Active-low default |
| GPB0 | Digital input | Ski lodge location | Active-low default |
| GPB1 | Digital input | Town location | Active-low default |
| GPB2 | Digital input | Spare | Active-low default |
| GPB3 | Digital input | Spare | Active-low default |
| GPB4 | Digital input | Spare | Active-low default |
| GPB5 | Digital input | Spare | Active-low default |
| GPB6 | Digital input | Spare | Active-low default |
| GPB7 | Digital input | Spare | Active-low default |

IR stations are NOT connected to MCP. MCP 0x20 GPB7 and 0x21 GPB2–GPB7 are spare: seven spare MCP pins total.

## Arduino Nano / Nano ESP32 — IR receiver controller

| Channel | Pin label | Direction | Receiver |
|---|---|---|---|
| 1 | D2 | Digital input | Tunnel entrance |
| 2 | D3 | Digital input | Yard entrance |
| 3 | D4 | Digital input | Ski entrance |
| 4 | D5 | Digital input | Tunnel exit east |
| 5 | D6 | Digital input | Tunnel exit west |
| 6 | D7 | Digital input | Underground entrance |
| 7 | D8 | Digital input | Tipper entrance |
| 8 | D9 | Digital input | Stall 1A |
| 9 | D10 | Digital input | Stall 1B |
| 10 | D11 | Digital input | Stall 2 |
| 11 | D12 | Digital input | Stall 3 |
| 12 | A0 | Digital input | Mine station |
| 13 | A1 | Digital input | Farm station |
| 14 | A2 | Digital input | Town station |

Reference board: classic 5 V Nano (ATmega328P). Alternative: 3.3 V Nano ESP32 (ESP32-S3). Same **labels**, separate board builds; respect different input voltage limits. USB only. Fourteen independent nonblocking decoder states, report valid DETECTED/CHANGED/CLEARED events plus requested snapshot; no continuous empty reporting. Production firmware is still pending. Other Nano pins not assigned to receivers are not automatically certified available.

## M5 Atom Echo — locomotive controller

| Pin | Direction | Function |
|---|---|---|
| GPIO19 | PWM output | DRV8871 IN1 / forward |
| GPIO22 | PWM output | DRV8871 IN2 / reverse |
| GPIO23 | 38 kHz output | IR transmitter transistor driver |
| 5 V / GND | Power | Regulated power and common ground |
| Unassigned | Input | Optional rearm switch not allocated |

## XIAO ESP32-C6 — locomotive controller alternative

| Pin | GPIO | Direction | Function |
|---|---|---|---|
| D7 | 17 | PWM output | DRV8871 IN1 / forward |
| D8 | 19 | PWM output | DRV8871 IN2 / reverse |
| D9 | 20 | 38 kHz output | IR transmitter transistor driver |
| 5V / GND | — | Power | Regulated power and common ground |

One physical locomotive uses M5 Atom Echo and one uses locomotive XIAO ESP32-C6. Both use rail pickups → bridge rectifier → filtered DC bus; bus feeds traction motor driver and 5 V regulator for controller. Rectifier is not yet selected. Locomotive controller pin assignments are distinct from accessory XIAOs.

## XIAO ESP32-C6 — rotary tipper USB controller

| Pin | GPIO | Direction | Function |
|---|---|---|---|
| D2 | 2 | Input | Hall front |
| D3 | 21 | Input | Hall rear |
| D4 | 22 | Input | Hall clear |
| D5 | 23 | Input | Encoder |
| D6 | 16 | Motor driver output | Rotation IN1 |
| D7 | 17 | Motor driver output | Rotation IN2 |
| D8 | 19 | Motor driver output | Lock IN3 |
| D9 | 20 | Motor driver output | Lock IN4 |
| D10 | 18 | Digital output | Decoupler relay (active-low) |

Hall inputs active-low. Encoder is 40-slot; calibration pending. Lock actuator runs for 800 ms (forward unlock/reverse lock). No separate IR station or Pi GPIO for this device. Other XIAO pins unassigned.

## XIAO ESP32-C6 — turntable USB controller

| Pin | GPIO | Direction | Function |
|---|---|---|---|
| D0 | 0 | Input | Home limit |
| D1 | 1 | Input | Rotated limit |
| D2 | 2 | Motor driver output | Rotation IN1 |
| D3 | 21 | Motor driver output | Rotation IN2 |
| D4 | 22 | Digital output | Polarity relay |
| D5 | 23 | Digital output | Track-power relay |
| D6 | 16 | Input | Reed end A |
| D7 | 17 | Input | Reed end B |

Switches and reeds active-low. All other XIAO pins unassigned. Verify relay polarities and track power isolation during commissioning.

## Classic Arduino Nano — dual-throttle USB controller

| Pin | Direction | Default function |
|---|---|---|
| D2 | Input | Left turnout LEFT |
| D3 | Input | Left turnout RIGHT |
| D4 | Input | Right turnout LEFT |
| D5 | Input | Right turnout RIGHT |
| D6 | Input | Left manual-enable (2 second hold) |
| D7 | Input | Right manual-enable (2 second hold) |
| D8 | Output | LCD RESET |
| D9 | Output | LCD D/C |
| D10 | Output | LCD SPI CS |
| D11 | SPI MOSI | LCD MOSI |
| D12 | SPI MISO | Unused by display |
| D13 | SPI SCK | LCD SPI clock |
| A0 | Analog input | Left throttle potentiometer |
| A1 | Analog input | Right throttle potentiometer |
| A2 | Unassigned | Spare |
| A3 | Unassigned | Spare |
| A4 | I²C SDA | Touch SDA |
| A5 | I²C SCL | Touch SCL |

This is the owner-confirmed classic Nano mapping, notwithstanding the divergent experimental Nano ESP32 sketch on HID_Dev. Buttons use pull-ups; 5 V Nano logic must be shifted to 3.3 V where required by the display/touch circuitry. Display controller ST7796U and FT6336U touch are provisional until module bench verification. Neutral + 5 s inactivity releases manual control; do not allocate the same train to both sides.

## Yard power relay outputs — intentionally unassigned

| Physical track | Stalls powered | Control pin |
|---|---|---|
| 1 | 1A + 1B, shared | Pending |
| 2 | 2 | Pending |
| 3 | 3 | Pending |

No fourth relay and no guessed Pi GPIO. All active default hardware assignments above must be represented by the web I/O Settings with edit/validation/persistence support; incomplete current UI coverage is an implementation task, not a reason to omit hardware from this document.

**Status rule:** Confirmed design does not mean tested wiring. Obsolete pin assignments are excluded from this active baseline; old archived drawings are not authoritative.
