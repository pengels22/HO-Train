# HO Railroad firmware and controller software inventory

**Hardware-first policy:** The Raspberry Pi 4B is the physical controller. Testing mocks are optional; running a railway simulator is not a prerequisite to controlling validated hardware.

| Device | Source | Current capability / limitation |
|---|---|---|
| Raspberry Pi 4B dispatcher | `railroad/` | Hardware-first control services with validated I/O registry, optional Pi I2C backends, edge-debounced reed events, and guarded yard outputs; bench commissioning remains required |
| M5 Atom Echo locomotives 1-4 | `locomotive_m5_atom_echo/locomotive_m5_atom_echo.ino` | Primary locomotive controller firmware; preserve and validate the existing safety/watchdog/IR implementation for all four units |
| Seeed XIAO ESP32-C6 turntable | `locomotive_esp32/turntable_esp32c6.ino` | Dedicated USB turntable controller; currently hardcodes four magnets and 250 ms lockout; requires configurable consist counting and compile/bench tests |
| Seeed XIAO ESP32-C6 rotary tipper | `tipper_controller/` | Dedicated accessory-controller assignment; protocol boundary exists, but controller firmware and board-specific pinout remain to be implemented and bench-tested |
| Arduino Nano 11 IR sensors | `ir_receiver/ir_receiver_nano_diagnostics.ino` | **New** non-actuating 11-input wiring/timing diagnostic; NOT the final 4-byte locomotive beacon decoder |
| Rotary tipper | Raspberry Pi GPIO and `railroad/automation/tipper.py` | Controlled from Pi per latest wiring plan; separate tipper-MCU serial firmware is not specified. Do not create an invented additional board |

## Current confirmed wiring plan
Raspberry Pi I2C: PCA9685 0x40 motor outputs, 0x41 spare, 0x42 servos; MCP23017 0x20 and 0x21 for 25 proposed NO reed sensors, seven spare inputs. Tipper GPIO5/6/17/22/23/24/25. Three proposed yard relay GPIO12/13/16 are *provisional* until harness checked. No direct relay-coil drive from Pi GPIO.

The M5 Atom Echo fleet carries the locomotive IR beacon and receives Pi dispatcher commands. Flex ferrite magnet strips on locomotive front truck and cars' rear trucks, between wheelsets; reeds across ties. Turntable and tipper target speed cap is **1 inch/s (25.4 mm/s)** measured using locomotive speed calibration, not arbitrary PWM.

## Build and hardware commissioning
1. Compile each sketch against its actual selected board and installed Arduino core; list core versions and dependencies when known.
2. Confirm wiring/polarity, idle outputs, motor-driver and relay power rails, and GPIO/input electrical levels.
3. First bench test the Nano diagnostic with one IR receiver; then implement/validate the decoder and actual optical packet format.
4. Bench test locomotive driver at zero speed, controlled ramp, loss-of-link stop, E-stop, and IR beacon.
5. Bench test turntable reeds using variable configured consist count, and rotation with track power isolated.
6. Implement/test Pi MCP/PCA/DRV drivers and tipper GPIO before running automatic routes.
7. Hardware should startup stopped; an operator can arm after checks. Do not require simulator or geometry certification for individual motor/sensor bench tests.

**Do not claim sketches are ready to flash based only on existence in Git.** 
