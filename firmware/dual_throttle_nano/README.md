# Classic Arduino Nano dual-throttle (HID_Dev)

**Status: first-pass, uncompiled/unflashed; no Pi transport integration is installed.**
This sketch MUST NOT be used for live motion until a Pi-side ownership gateway and watchdog have been implemented, tested, and reviewed.

## Hardware

- Board: Arduino Nano classic, ATmega328P, 5V.
- Potentiometers: 10k linear center detent. Left A0, right A1; each end to 5V/GND; 100nF from wiper to GND.
- Buttons: internal INPUT_PULLUP, normally-open to GND.
  - D2 left handle / turnout left; D3 left handle / turnout right.
  - D4 right handle / turnout left; D5 right handle / turnout right.
  - D6 left thumb enable; D7 right thumb enable.
- Screen: ST7796U 480x320 RGB565 on SPI D11 MOSI, D13 SCK; D10 CS, D9 D/C, D8 RESET. D12 MISO unused by the minimal driver.
- Touch: FT6336U over I2C A4 SDA, A5 SCL, default 0x38.
- **5V Nano outputs must be level shifted to 3.3V display inputs; I2C must use a 3.3V compatible bidirectional level shifter and 3.3V pull-ups.** Display VCC follows its specific module supply specifications.
- Display controller init/rotation and touch coordinates are **not verified** against the Travel Laser Controller hardware; use bench confirmation before connecting.
- Library: Adafruit GFX; built-in SPI/Wire/EEPROM.

## Operator states

- Left/right side selection starts at 1/2, respectively.
- Only trains 1–4 selectable. Opposite selection is skipped even when opposite side is in standby.
- Selection requires neutral, standby, online link, and Pi acknowledgment.
- Hold D6/D7 continuously 2000ms while neutral to request manual authority.
- Pi `GRANT` enters ACTIVE; only ACTIVE sends signed motion commands. Center is zero.
- Five seconds of neutral without turnout interaction releases manual authority.
- Reconnect requires neutral and a new two-second hold; all previous authority is dropped locally.
- Pi must reject any duplicate selections, conflicting controller owners, unsafe turnout requests, missing authorization, and stale commands. The Nano-side checks are not a substitute.

## USB ASCII protocol (115200 8N1)

One command per line. This is a proposed protocol, **not yet wired into** `railroad/`.

Nano -> Pi:

```
HELLO NANO_DUAL_THROTTLE 1
PING
SELECT L 3
ACQUIRE L 3
MOTION L 3 -37
TURNOUT L 3 LEFT
RELEASE L 3
```

Pi -> Nano:

```
READY
PONG
ASSIGN L 3
GRANT L 3
DENY L 3
RELEASED L 3
```

The Pi must keep per-USB-session ownership records and independently time out stale heartbeat/motion. The first firmware pass treats any PONG/READY as a heartbeat: **a production bridge must bind response messages to a validated session** and reject stale/mismatched replies. The Nano sends 120ms repeated motion commands while ACTIVE; losing the Pi heartbeat for >1500ms fails closed locally. The Pi must independently stop a manually controlled locomotive much faster than any unsafe coasting interval established by hardware testing, and never rely on receiving RELEASE after USB unplugging.

## Calibration

Three values per lever: reverse, center, forward, each 0–1023. EEPROM storage is implemented with checksum validation. A calibration UI and calibration command **are not implemented**. Defaults are 0/512/1023 and are placeholders; physical stops likely reduce available throw. Do not commission motion until actual end-stop and center values are measured and written. Near-center neutral uses ±16 ADC counts; tune after bench testing.

## Remaining work / blockers

1. Verify ST7796 initialization, scan direction, capacitive touch orientation and read timing against the exact Travel Laser Controller screen.
2. Memory and sketch flash-size compilation on classic Nano (32KB flash, 2KB SRAM). Rendering currently redraws the entire 480×320 control screen; benchmark and replace with partial region updates if too slow.
3. Add a Pi USB serial ownership gateway with bounded parsing, negative acknowledgments, startup/restart reconciliation, and per-device watchdog.
4. Add a calibration flow and persistent values including reverse/forward orientation.
5. Bench-test potentiometer faults, button debounce, lost USB, direction transitions, manual ownership conflicts, and global stop interlocks.
6. Validate 5V/3.3V logic shifting for the actual display module.

**Never deploy to live locomotives based on this first-pass sketch alone.**
