# HO Railroad firmware and controller software inventory

**Hardware-first policy:** The Raspberry Pi 4B is the physical controller. Testing mocks are optional; running a railway simulator is not a prerequisite to controlling validated hardware.

| Device | Source | Current capability / limitation |
|---|---|---|
| Raspberry Pi 4B dispatcher | `railroad/` | Hardware-first control services with validated USB Firmata I/O registry, edge-debounced Mega reed events, and guarded yard outputs; commissioning remains required |
| M5 Atom Echo locomotives 1-4 | `locomotive_m5_atom_echo/locomotive_m5_atom_echo.ino` | Primary locomotive controller firmware; preserve and validate the existing safety/watchdog/IR implementation for all four units |
| Seeed XIAO ESP32-C6 locomotive bench variant | `locomotive_xiao_esp32c6/locomotive_xiao_esp32c6.ino` | Optional board-specific port of the M5 protocol; D7/GPIO17 and D8/GPIO19 motor PWM, D9/GPIO20 IR transmitter; not the dedicated tipper board |
| Seeed XIAO ESP32-C6 turntable | `turntable_esp32c6/turntable_esp32c6.ino` | Dedicated USB turntable controller with per-consist count and stable reed edge debounce; compile and bench-test relay polarity, limit switches, and mechanical timeout |
| Seeed XIAO ESP32-C6 rotary tipper | `tipper_esp32c6/tipper_esp32c6.ino` | Dedicated accessory controller using the supplied GPIO map: rotation 16/17, gripper 19/20, decoupler 18, Hall 2/21/22, encoder 23; verify polarity and mechanics |
| Arduino Nano 11 IR sensors | `ir_receiver/ir_receiver_nano_diagnostics.ino` | **New** non-actuating 11-input wiring/timing diagnostic; NOT the final 4-byte locomotive beacon decoder |
| Arduino Nano ESP32 bench IR | `ir_receiver_nano_esp32_bench/ir_receiver_nano_esp32_bench.ino` | One D2 receiver with persistent logical endpoint and test train selection; non-actuating |
| Rotary tipper | Dedicated XIAO ESP32-C6 over USB serial; Pi dispatcher interface in `railroad/automation/tipper.py` | Motor, lock, decoupler, sensors, and encoder are C6-owned; outputs start disabled and require explicit rearm |

## Current confirmed wiring plan
The Firmata migration uses an Arduino Mega 2560 for the seven motor pairs,
crossing servos, and 28 reed inputs, plus an Arduino Nano Classic for the
active-low turnout and yard relays. The Nano ESP32 owns the IR endpoint map.
The rotary tipper and turntable remain dedicated XIAO ESP32-C6 controllers.
The former Pi I²C inventory is compatibility-only and is not opened by the
Firmata runtime. No direct relay-coil drive from Pi GPIO.

The M5 Atom Echo fleet carries the locomotive IR beacon and receives Pi dispatcher commands. Flex ferrite magnet strips on locomotive front truck and cars' rear trucks, between wheelsets; reeds across ties. Turntable and tipper target speed cap is **1 inch/s (25.4 mm/s)** measured using locomotive speed calibration, not arbitrary PWM.

## Build and hardware commissioning
1. Compile each sketch against its actual selected board and installed Arduino core; list core versions and dependencies when known.
2. Confirm wiring/polarity, idle outputs, motor-driver and relay power rails, and GPIO/input electrical levels.
3. First bench test the Nano diagnostic with one IR receiver; then implement/validate the decoder and actual optical packet format.
4. Bench test locomotive driver at zero speed, controlled ramp, loss-of-link stop, dispatcher broadcast STOP (`0x80` legacy wire flag), and IR beacon.
5. Bench test turntable reeds using variable configured consist count, and rotation with track power isolated.
6. Commission the Mega/Nano Firmata adapters and the tipper C6 serial
   interface before running automatic routes. Legacy Pi MCP/PCA/DRV modules
   are migration compatibility only.
7. Hardware should startup stopped; an operator can arm after checks. Do not require simulator or geometry certification for individual motor/sensor bench tests.

**Do not claim sketches are ready to flash based only on existence in Git.**
