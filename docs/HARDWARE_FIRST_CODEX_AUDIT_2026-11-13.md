# HO-Train: hardware-first implementation audit and Codex work order
Date: 2026-11-13
Repository: pengels22/HO-Train, main (read-only audit)
Status: action plan; NOT a claim that hardware is working or tests passed.

## Instruction to Codex
Implement the HO railroad as an actual Raspberry Pi 4B-controlled model railway, NOT a simulation-first demonstration. Hardware mode is the primary product. Do not make running a simulator, having surveyed polygon geometry, or manually flagging every track segment as verified a prerequisite to bench control. Keep simulation/test doubles optional for automated testing and development on a Mac. Keep startup outputs OFF, physical E-Stop, controller-local watchdogs, current fuses, switch interlocks and global stop on lost checkpoints; do not substitute new bureaucratic approval gates for functionality. Do not enable live train motion just because this document exists. Build and test each physical interface in controlled bench mode, then explicitly arm it for use.

## Verified repository findings
- `railroad/main.py` defaults to `simulation`; `railroad/api/server.py` instantiates `SimulationEngine` globally and configures hardware only with substantial gating. The dashboard is heavily simulation-oriented.
- `railroad/hardware/mcp23017.py`, `pca9685.py`, `drv8833.py`, and `i2c.py` are placeholders. Real sensor polling, output writes, and commissioning tools are not implemented.
- `config/sensors.yaml` has global 250 ms debounce, twenty-four A-H turnout positions and four destination detectors: 28 populated inputs. The newer confirmed A-G layout requires 21 turnout detectors + 4 location detectors = 25 inputs, leaving 7 spares on two MCP23017 boards.
- `railroad/dispatcher.py` and `railroad/routing/interlocking.py` still include turnout H. `config/track_layout.yaml` and `config/turntable.yaml` also reference H/UND-4; `tests/test_turntable_safety.py` tests H. This CONFLICTS with the latest 7-powered-turnout A-G wiring plan. Do not silently remove H or break turntable routing: isolate a decision/configuration switch and present topology reconciliation, defaulting current confirmed hardware to A-G while leaving turntable access unresolved until mapped to the real track.
- `config/yard_power.yaml` declares three relays but all outputs `unassigned`; `railroad/yard.py` understands 1A and 1B share Track 1.
- `config/motors.yaml` maps 8 pairs to PCA9685 0x40; `config/servos.yaml` maps A-G and the tipper lock to PCA9685 0x42, plus provisional H on channel 13. Board 0x41 is reserved/spare.
- `railroad/turntable.py`, `firmware/locomotive_esp32/turntable_esp32c6.ino` and `config/turntable.yaml` hard-code exactly 4 magnet detections and a 250 ms pulse lockout. `tests/test_turntable_safety.py` and `tests/test_controller_lifecycle.py` assume 0.3-second pulses; this is not the new physical detection scheme.
- `railroad/automation/tipper.py` has a safety-state skeleton and an unconnected serial adapter; `firmware/tipper_controller/README.md` explicitly says the tipper control firmware does not exist.
- `firmware/locomotive_esp32/locomotive_esp32.ino` is an uncommissioned prototype and is not a locomotive assignment. The finalized architecture assigns `firmware/locomotive_m5_atom_echo/` to all four locomotives; dedicated XIAO ESP32-C6 boards are assigned to turntable and rotary tipper control.
- `config/locomotives.yaml` speed calibration is null; `Dispatcher.command_motion` accepts a raw signed speed number and lacks destination-specific measured in/s caps.
- `docs/PROJECT_STATUS.md`, `docs/CONTROLLER_DECISIONS.md`, `docs/CONFIGURATION_SOURCES.md` and README say simulation-first; rewrite truthfully after actual changes.
- Network E-Stop, explicit rearm and telemetry mechanisms are real, valuable work; preserve them. Tests exist but have NOT been executed by this audit.

## Finalized hardware & physical facts
- Raspberry Pi 4B is the central dispatcher. Main loop track feed 12 V DC, fused 7 A; rotary tipper isolated rail section with separate fused 2 A feed, same 12 V supply; 1/6-inch gaps at both ends. Auxiliary 5 V 18 A PSU for motors and servos, 5 A servo branch, 1 A per DRV8833 branch. Separate fused 16 V decoupler branch. Shared signal ground and properly routed power returns.
- I2C: two MCP23017 input boards at 0x20 and 0x21; PCA9685 motor outputs 0x40, expansion 0x41, servo outputs 0x42. Electrical I2C levels/power rails must be bench-verified. No GPIO is permitted to source a relay or motor directly.
- PCA9685 0x40 CH0/1 mine lift, 2/3 ski chairlift, 4/5 grain auger, 6/7 farm magnetic road, 8/9 ski lodge magnetic road, 10/11 long-haul road, 12/13 town magnetic road, 14/15 rotary tipper motor; each paired to a driver. 0x41 spare.
- PCA9685 0x42 CH0 farm gates, CH1 A, CH2 B, CH3 C, CH4 town gates, CH5 yard1, CH6 yard2, CH7 yard3, CH8 tipper spring-engaged wheel lock (servo pulls DOWN to release), CH9 D, CH10 E, CH11 F, CH12 G, CH13-15 spare unless H is physically verified. Mine ore lift has ONE motor; tipper restraint is passive.
- 3 actual powered yard tracks: Track 1 stalls 1A and 1B share a SINGLE relay, Track 2 stall 2, Track 3 stall 3. Keep parked train identity while de-energized.
- Tipper Pi BCM GPIO assignments from existing electrical design: 22 IR front clear HIGH; 23 IR back clear HIGH; 24 Hall back active LOW; 25 Hall front active LOW; 5 Hall clear active LOW; 17 tipper encoder; 6 decoupler relay control. These dedicated tipper Hall sensors may remain Hall type: do not indiscriminately replace them with the track reed sensor schema.
- Yard relay proposed GPIO12, GPIO13, GPIO16 for tracks 1/2/3, but VERIFY they do not conflict with actual E-stop and other Pi wiring; keep configurable until physically confirmed. GPIO physical numbering and BCM distinction must be explicit.
- At 0x20: GPA0/1/2 A common/straight/diverging; GPA3/4/5 B; GPA6/7 GPB0 C; GPB1/2/3 D; GPB4/5/6 E; GPB7 spare. At 0x21: GPA0/1/2 F; GPA3/4/5 G; GPA6 mine, GPA7 farm, GPB0 ski, GPB1 town; GPB2-7 spare. All are normally-open reed sensors with pullups, active-low, if bench tests validate the chosen magnet/tape.
- Every locomotive and railcar has one flexible ferrite tape magnet, target cut ~1 x 0.5 x 0.063 inches, mounted BETWEEN AXLES on underside of a truck. Locomotive = front truck, cars = rear truck. Confirm fit and activation before adopting globally. Reed switches mounted across track parallel to ties, recessed in ballast gap between ties. Validate field orientation and one stable pulse per pass.
- Reed timing: replace global 250 ms debounce with configurable edge debounce initially 10-20 ms (tune from bench trace); require verified CLOSED->OPEN cycle to count each car, with no fixed 250 ms pulse lockout. Do not equate 1-inch magnet length to guaranteed 1000 ms closed interval.
- Tipper AND turntable, when the TARGET destination, have MAX PHYSICAL train velocity of 1 inch/second = 25.4 mm/s. Enforce on both joystick and dispatcher paths and BEFORE entry into counting section, using calibrated per-loco PWM/direction speed mapping. Unknown calibration -> no automatic motion to these destinations (do not pretend raw PWM is mm/s). Calculate stopping approach from calibration; avoid hard-coding PWM=some speed. Commands after a target change must obey the same limit.
- Train orientation is a POSSIBLE inference using asymmetric locomotive-front vs cars-rear magnet timing, observed pulse spacing, known geometry and IR locomotive identity; produce FORWARD/REVERSE/UNKNOWN with confidence, not an unqualified guess. Individual Hall/reed clear between cars NEVER proves the entire consist cleared a zone.
- Turntable uses its distinct XIAO ESP32-C6 USB controller, two reed-end inputs and alignment/polarity/track-power interlocks. Its expected magnet count MUST be derived from configured consist (loco + trailing cars, as equipped), not constant four. Track topology H vs A-G unresolved, no invented switch routes.
- 4 locomotives, 1 passenger assigned to ski, 3 freight; preserve freight ore/corn rule (tipper unload between sources), 15 existing logical zones, no two trains in same zone/destination, one train per destination, missed IR checkpoint = latched global stop. Tipper ACTIVE/FAULT blocks MAIN-3 and UND-1, while MAIN-2 to Mine via A is permitted on a validated route.
- Logitech Attack 3 buttons 2-5 select trains 1-4, trigger/B1 enables control, Y axis speed, X axis switch selection, Z ignored, deadzone 20 in joystick's actual axis units (do not confuse 20 normalized with 20 raw). Selection resets MANUAL speed to zero.

## Implementation order: deliver functional hardware rather than a simulator
### Phase 1: configuration and hardware foundation
1. Create single typed hardware I/O registry (board/address/channel/BCM, device type, location, polarity, active status, spare) with validation of duplicates, reserved Pi pins, incompatible levels and collisions.
2. Replace I2C, MCP23017, PCA9685, DRV8833 stubs with explicit Raspberry Pi backends and unit-tested mock backends. Expose safe I2C scan, input monitor, servo jog, motor jog, output OFF. Do NOT start actuators on import or web request.
3. Implement reed input events with stable-edge debouncing, timestamped CLOSED/OPEN pulses, duration and per-sensor counters; retain separate tipper IR/Hall input types. Use MCP23017 interrupt-on-change or adequately fast polling, with diagnostic traces.
4. Implement three yard DC relay outputs as configured, default OFF; require zero traction speed and track reservations for energization and ensure shared Track 1 behaves correctly.
5. Implement GPIO tipper IO and motor/servo/decoupler interfaces, maintaining passive restraint logic, encoder/home alignment and a fail-safe motor-off state.
6. Allow physical E-stop pin to be configured without colliding with the chosen tipper or yard pins. Keep the original E-stop behavior (NC switch, LOW active) and global latch. Avoid motor or relay writes when connections fail.

### Phase 2: real locomotives and speed
7. Preserve and validate the existing M5 Atom locomotive controller for all four locomotives: Wi-Fi UDP packet handling, IR 940 nm beacon, telemetry, watchdog, safe starts, explicit rearm, and motor drive. Use dedicated XIAO ESP32-C6 controllers for the turntable and rotary tipper; verify each board's memory, compile, and pin mapping without guessing.
8. Add real speed calibration data in in/s or mm/s by throttle command and direction. Implement enforceable target cap <=25.4 mm/s for both TIPPER and TURNTABLE across ALL motion pathways, including joystick, API, route cycles, recovery and target changes. Test cap from above; never bypass via direct `command_motion`.
9. Build Raspberry Pi joystick input adapter for Attack 3; manual control must still honor stop, zone, yard and speed limits.

### Phase 3: tipper, turntable and tracking
10. Tipper state machine: approach at <=1 in/s, confirm counted truck magnets and positioning, confirm IR Front/Back and Hall Front/Back/Clear, stop train, spring-engaged lock, rotate via M8 and encoder with timeouts, dump, return/home, release lock and depart, enforce protected zones. Handle multiple cars and unexpected extra/missing pulses with stop.
11. Turntable: use XIAO USB controller and configurable expected consist count, two end reeds, stable pulse events, known alignment, positive stationary/clearance feedback, motor OFF before polarity changes, track power OFF during rotation, rearm after any fault. Remove rigid four-pulse assumption. Preserve two-end asymmetry.
12. Train orientation optional inference, not authoritative for collision safety. Record sensor pulse timing and evidence; integrate with locomotive IR checkpoints, target and dispatch records; expose UNKNOWN when data insufficient.
13. Implement true topology from verified physical track routing; avoid fabricating turntable H connectivity. Reconcile the repo's H turnout with A-G design; preferably a migration/spec review separating turntable-access turnout from counted motorized A-G roster. Until resolved, block only unknown route segments, not all unrelated hardware bench features.

### Phase 4: operator UI and deployment
14. Make dashboard launch directly in hardware mode on Pi. Provide live trains, speed in in/s, target, direction/uncertainty, active reed sensors/pulses, turnout position, tipper/turntable states, 3 yard relay statuses, E-stop latch, faults and test controls. Never label simulated positions as live positions.
15. Implement requested SETTINGS I/O table for EVERY GPIO, MCP23017 0x20/0x21 and PCA9685 0x40/0x41/0x42 pin/channel, configured or spare, board, address, direction, logical function, polarity, current status; filter/edit/validate/save/persist. Include explicit per-sensor debounce and count mode. Preserve the source layout image and editor overlays.
16. Rewrite service file and README for Raspberry Pi 4B hardware-first startup with idle/disarmed outputs and operator-initiated arm. Keep a separate `--mode simulation` or `--mode test` for developer purposes only, not a required stage or default route.
17. Maintain a concise deployment checklist: wiring/current/logic validation; one-sensor magnet test; no-car unloaded motor jog; zero-speed calibration; one train under 1 in/s approach; E-stop and lost-comms checks.

## Required automated tests
- 25 track inputs, 7 spares, no duplicate pin mappings, no accidental 8th turnout in configured A-G hardware; H discrepancy reported rather than silently erased.
- Two reed transitions in quick succession do not disappear due to 250 ms lockout; switch bounce does not double count; closure lasting >1 s is one pulse; no counting until an OPEN edge has been observed.
- N magnet pulses count N vehicles using configured consist; N+1 faults; missing last-car evidence retains the reservation.
- Turntable and tipper cap <=25.4 mm/s for automatic, manual, direct dispatch, and during target changes; unknown speed calibration cannot enable automatic 1 in/s positioning.
- Tipper encoders/IR/Halls contradictory or missing -> stop; tipper ACTIVE/FAULT locks MAIN-3 and UND-1 but validated MAIN-2->Mine route remains possible.
- Exactly three yard power outputs; Stalls 1A/1B always share relay 1; parked identities retained and other parked loco cannot unintentionally move when shared track powered.
- E-stop local motor/relay shutdown, communication watchdog, global checkpoint stop, no automatic restart/rearm.
- Default physical startup = OFF/DISARMED and no writes until explicitly selected hardware interface and arm.
- Every existing regression test updated when specs legitimately change; don't delete tests to make suite green. Run `pytest`, report actual failures and firmware compile status separately.

## Codex working method
- Read AGENTS.md and current git status first. Create focused commits and PR(s); avoid wholesale rewrites.
- First commit: central configuration/schema, corrected A-G sensor mapping, debounce event class, tests, and docs. Next commits: real Pi hardware driver; speed limit; tipper/turntable; UI. Keep unfinished features clearly marked, not described as functioning.
- Treat all provisional pins and board-specific ESP32 pinouts as unverified until checked against actual wiring and board docs. The 2026-11-13 master wiring plan has SOME proposed assignments (yard GPIO12/13/16) rather than a verified physical harness.
- Do NOT let the previous 250 ms `debounce_ms` accidentally become train-pulse event lockout. Separate contact debounce from minimum-clear timing and count completion.
- Do NOT insist on simulation-gated `verified: true` geography just to test a motor or sensor. No blanket requirement for manual per-zone geometry certification. Route-specific unknown geometry can remain blocked for unattended dispatch.
- Keep changes understandable and practical for a home HO train layout. Physical safety interlocks protect the equipment; there is no requirement for aerospace-style ceremony.
