# HID_Dev — Dual-Throttle Human Interface Controller

Status: **approved design baseline; implementation not started**
Branch: `HID_Dev`
Recorded: 2026-11-15

## Intent and ownership

A dedicated **Arduino Nano ESP32** connects to the Raspberry Pi railroad dispatcher over **USB serial**. It reads two physical throttles and four turnout buttons and operates a **single 3.5-inch color SPI touchscreen** shared between two throttle panels. The console is an input/display accessory, **not a second train dispatcher**.

The Raspberry Pi dispatcher owns normal automatic running, routes, turnout interlocks, train identity and position, zone occupancy, reservations and collision prevention.

- **AUTO**: dispatcher commands speed, direction, destinations and turnouts; the console displays dispatcher-confirmed state.
- **MANUAL**: operator commands the selected locomotive's signed speed/direction with its potentiometer and requests the approaching turnout path with LEFT/RIGHT buttons. Dispatcher still tracks the train and enforces safety/occupancy/turnout interlocks; unsafe commands must be rejected.
- Select a locomotive independently on each half of the touchscreen using **+ / −**. Skip the train number assigned to the opposite half; one locomotive may have at most one manual throttle owner.
- Keep selections and operating mode independent for the two halves. Unselected locomotives may continue operating automatically.
- On selection or AUTO→MANUAL handoff, prevent an immediate throttle jump (require pickup/zero-speed confirmation or another explicitly safe handoff before accepting potentiometer movement).
- On MANUAL→AUTO handoff, do not unexpectedly accelerate; resume automatic movement only when dispatcher authorizes.
- STOP applies to the selected locomotive; existing dispatcher global-stop behavior remains available separately. Missed IR checkpoints retain their previously agreed global-stop response.
- Console disconnection must not send stale manual throttle values; the dispatcher should expire manual authority and command the affected train to a safe stop while leaving unaffected trains operational.

## Display and physical controls

- Reuse the **same 3.5-inch touchscreen module used on the Home Control Modules and existing laser controller**.
- **Display module power input: 5 V**, **SPI / I²C logic: 3.3 V**; this electrical arrangement is already operating on the laser controller.
- 480×320 landscape GUI is the current design target; confirm the exact panel and touch-controller identifiers before writing display drivers.
- Divide the screen vertically into **two 240-pixel-wide control areas**, one per throttle.
- Each side: **train number with + / − selection**, train speed and direction display, destination, **AUTO / MANUAL selection**, and relevant status/alerts.
- Physical controls: **two center-detent potentiometers** (one per throttle); fully counterclockwise = reverse, center = stop, clockwise = forward. Calibrate true center, use a small configurable deadband, and transmit a signed throttle demand.
- Physical turnout controls: **two momentary buttons above each throttle**: LEFT and RIGHT. Each press requests the appropriate path at the upcoming turnout for that selected train *in its direction of travel*. Map LEFT/RIGHT to physical turnout position for each approach; do not assume it means servo rotation direction or straight/diverging universally. In AUTO the buttons do not override dispatcher routes.
- No physical forward/reverse switches or extra direction touchscreen controls are required.

## Hardware inventory

| Item | Quantity | Interface |
| --- | ---: | --- |
| Arduino Nano ESP32 (ESP32-S3) | 1 | USB serial to Raspberry Pi |
| Existing HCM/laser-controller 3.5-inch touchscreen module | 1 | SPI LCD, I²C touch if confirmed |
| ADS1115 | 1 | I²C, proposed address 0x48 |
| Center-detent potentiometers | 2 | ADS1115 A0 and A1, 0–3.3 V |
| Momentary turnout LEFT/RIGHT buttons | 4 | Nano GPIO, active-low with pull-ups |

## Accepted proposed Arduino Nano ESP32 pin allocation

| Arduino Nano ESP32 label | Assignment |
| --- | --- |
| D13 | LCD SPI SCK |
| D11 | LCD SPI MOSI |
| D12 | LCD SPI MISO, **only if required by module** |
| D10 | LCD chip select |
| D9 | LCD data / command |
| D8 | LCD reset |
| D7 | Throttle A LEFT |
| D6 | Throttle A RIGHT |
| D5 | Throttle B LEFT |
| D4 | Throttle B RIGHT |
| A4 | Shared I²C SDA — ADS1115 and touch controller |
| A5 | Shared I²C SCL — ADS1115 and touch controller |
| ADS1115 A0 | Throttle A potentiometer wiper |
| ADS1115 A1 | Throttle B potentiometer wiper |
| USB-C | Power / serial to Pi |

This is an **approved proposed pinout**, not a tested or flashed Nano firmware mapping. Validate actual pin multiplexing against the installed Nano ESP32 board core and chosen display harness. Do not assign these pins to the Raspberry Pi, tipper XIAO or turntable XIAO.

## Power and electrical assumptions

- Nano ESP32 is USB-powered and operates at 3.3 V GPIO logic.
- Touchscreen module takes **5 V input** but requires **3.3 V data signaling**. Do not power its 5 V input from a 3.3 V rail.
- ADS1115 and potentiometers use 3.3 V; button inputs are active-low with pull-ups.
- All signals share ground.
- Confirm touchscreen backlight and total current consumption before deciding whether the USB 5 V feed can supply the entire console.
- Display touch controller, I²C address, LCD driver, chip-select/control lines and 5 V connector pinout require verification against the physical module/known working laser-controller build.

## Serial messages and operator authority (design intent)

- Use simple framed messages with a **fixed firmware module number** burned into the Nano build and echoed in each command/status message. Include message boundary, length or equivalent framing, a sequence/transaction field to match commands and replies, and a basic integrity check if using binary framing.
- Console→Pi: throttle side, selected train, AUTO/MANUAL request, signed throttle, LEFT/RIGHT turnout request, STOP, button/connection state.
- Pi→console: confirmed selected train and authority, actual speed/direction, destination, next turnout and path, mode, reason for rejected commands, controller-health status.
- The Pi is authoritative for the two throttle assignments, so reconnects or competing consoles cannot create duplicate ownership.
- The console is independent of the **bench Nano IR reader**. The bench IR decoder is troubleshooting equipment only; the permanent destination IR network is a separate subsystem.

## Commissioning and acceptance checks

1. Confirm exact LCD/touch hardware from the proven laser-controller wiring; verify 5 V display input and 3.3 V logic.
2. Confirm SPI display drawing and touch input alongside ADS1115 I²C reading without bus/address conflicts.
3. Measure both center detents; verify zero deadband, signed reverse/forward and noise filtering.
4. Verify four momentary buttons and one-event-per-press debounce.
5. Test train cycling on both panels and exclusion when the other panel already owns a train.
6. Test AUTO/MANUAL takeover without a speed jump, disconnected-console stop, and dispatcher authorization.
7. Test turnout LEFT/RIGHT against real train travel direction and switch physical geometry, rejecting occupied/unsafe changes.
8. Verify Pi serial reconnect and fixed module identity.
9. Do **not** drive live locomotives or turnouts until the required integration tests and mechanical checks pass.

## Adjacent project decisions (do not implement as HID-only changes)

- Existing tipper and turntable remain on their separate XIAO controllers.
- No direct Raspberry Pi GPIO accessory assignments and no new physical E-stop hardware.
- Tipper lock is a timed motor operation, not a sensor.
- Lab 1 deployment, locomotive firmware, permanent Nano IR network, and full dispatcher redesign are separate follow-on tasks.
- H and UND-4 are valid parts of the layout topology.
- Missing locomotive speed calibration must not crash unrelated operations; calibrated automatic slow approach remains unavailable until measured.

This design document records the user-approved console architecture; it does **not** claim any source firmware, Pi runtime or physical hardware has been changed.
