# Arduino Nano ESP32 — dual-throttle HID (first-pass)

This is a **development firmware/UI prototype**, not a deployed or hardware-verified train controller. It only sends **requests** to the Pi; no train or servo can be driven directly by this sketch.

## Dependencies
- Arduino IDE / Arduino CLI with **Arduino Nano ESP32** board package (ESP32-S3)
- **GFX Library for Arduino** (Arduino_GFX_Library)
- **Adafruit ADS1X15**
- **ArduinoJson 7**

Set board **Arduino Nano ESP32**. This sketch assumes the proposed display is compatible with **ST7796**; verify the actual screen controller from the working laser-controller build first. If different, change the \`Arduino_ST7796\` constructor and the guarded display driver block. Set \`HID_LCD_ST7796=0\` to compile/bench-test inputs and serial *without drawing the GUI*.

**Touch is disabled by default** (\`HID_TOUCH_FT6336=0\`) until its I²C touch-controller identity is verified. Enable only when the installed module actually uses FT6336U/FT6236-style registers and orientation is confirmed. \`HID_TOUCH_SWAP_XY\` and axis-invert flags provide basic alignment options. For a different touch IC, replace \`readTouch()\`. The touchscreen train selector and AUTO/MANUAL buttons will only be interactive after touch is enabled and working.

## Pinout
| Arduino label | Device |
|---|---|
| D13 SCK, D11 MOSI, D12 MISO (optional) | SPI LCD |
| D10 CS, D9 DC, D8 RST | LCD |
| D7 / D6 | Throttle A LEFT / RIGHT button to ground |
| D5 / D4 | Throttle B LEFT / RIGHT button to ground |
| A4 SDA / A5 SCL | ADS1115 + display touch I²C |
| ADS1115 A0, A1 | Two center-detent throttle potentiometer wipers |

LCD **5 V input**, **3.3 V signal logic**. ADS1115/pots **3.3 V**, shared ground. USB serial at **115200 baud**. Check display backlight/USB current before powering through Nano.

## UI first pass

480×320 landscape split into two 240 px panels. Train number ±, confirmed speed/direction, destination and next turnout, AUTO / MAN selection, STOP request, current status. Four physical button inputs are debounced and send upcoming-turnout LEFT/RIGHT requests only in Pi-confirmed MANUAL mode.

The two throttle selectors skip the train owned by the other panel locally, while the **Pi remains authoritative for exclusive ownership**.

## Serial protocol v0 (STX + JSON + LF)

Every message is ASCII **STX (0x02)**, compact JSON payload, **LF (0x0A)**. The \`sof\` property is \`"HID1"\`, \`module\` is compile-time module ID (prototype **17**, change before flashing a second unit), and \`seq\` increments per outbound message. This is not yet a production integrity-checked protocol. **Do not connect request messages directly to motor control.** Implement a Pi-side command validator and state sender first.

Nano→Pi examples (each shown *without* leading STX):
\`\`\`json
{"sof":"HID1","module":17,"seq":1,"type":"HELLO"}
{"sof":"HID1","module":17,"seq":2,"type":"SELECT","side":"A","train":3}
{"sof":"HID1","module":17,"seq":3,"type":"MODE","side":"A","train":1,"mode":"MANUAL"}
{"sof":"HID1","module":17,"seq":4,"type":"THROTTLE","side":"A","train":1,"speed":-40}
{"sof":"HID1","module":17,"seq":5,"type":"TURNOUT","side":"B","train":2,"path":"LEFT"}
{"sof":"HID1","module":17,"seq":6,"type":"STOP","side":"A","train":1}
{"sof":"HID1","module":17,"seq":7,"type":"PING"}
\`\`\`

Pi→Nano example, mandatory after HELLO, SELECT and MODE; repeated periodically (≤ ~500 ms) to maintain the 1500 ms link timeout:
\`\`\`json
{"sof":"HID1","module":17,"seq":120,"type":"STATE","panels":[{"train":1,"mode":"MANUAL","speed":0,"destination":"FARM","next_turnout":"C","notice":"READY"},{"train":2,"mode":"AUTO","speed":64,"destination":"SKI","next_turnout":"D","notice":"READY"}]}
\`\`\`
Pi→Nano \`{"sof":"HID1","module":17,"seq":121,"type":"REJECT","side":"A","reason":"ROUTE OCCUPIED"}\`. \`PONG\` with the same module ID refreshes link health.

**Protocol implementation is only on the Nano** at this stage. No Pi receiver or dispatcher motor-command integration was created.

## Safety behaviors
- Fresh Pi \`STATE\` required before accepting manual control or train-selection requests.
- Switching train selection or mode blocks controls until Pi acknowledges via \`STATE\`.
- Entering MANUAL requires the physical knob to reach the center-zero detent before signed throttle commands are emitted (no accidental speed jump).
- Changing modes or assignment resets local pickup state. AUTO ignores analog demand.
- Console drops manual authority locally after 1.5 seconds without Pi state/heartbeat; Pi **must independently** time out manual demand, set the affected locomotive to zero and preserve unaffected trains.
- STOP is an individual-locomotive request, subject to Pi identity checks.
- TURNOUT requests convey LEFT/RIGHT for the *approaching train*, not a servo angle.
- No direction buttons; sign of potentiometer sets forward/reverse.
- No direct Raspberry Pi GPIO control.

## Hardware work still needed
1. Confirm actual LCD driver + touch IC and orientation from working HCM/laser controller; wire backlight appropriately.
2. Verify Nano pin numbering, display power budget and bus sharing.
3. Set actual ADC centered reading and deadband after measuring detents; ADS1115 \`GAIN_ONE\` scaling assumes a 3.3 V supply.
4. Add a Pi-side state/authorization receiver in a separate change.
5. Run compile, screen/touch, ADS1115, button, disconnect and turnout-interlock tests.
