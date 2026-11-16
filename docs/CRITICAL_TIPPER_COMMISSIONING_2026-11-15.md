# Tippler control corrections — 2026-11-15

## Architecture
- Single tipper controller: Seeed XIAO ESP32-C6.
- No Raspberry Pi GPIO connections or tipper train-clearance IR inputs.
- Track Hall sensors: D2/GPIO2 Front, D3/GPIO21 Back, D4/GPIO22 Clear.
- Optical encoder: D5/GPIO23; 40 slots, wheel diameter 1.125 inches.
- Rotation motor: D6/GPIO16, D7/GPIO17.
- Lock actuator: D8/GPIO19, D9/GPIO20; 800 ms timed action, no lock sensor.
- Decoupler: **D10/GPIO18, active LOW**, timed 250 ms pulse.
- PCA9685 motor CH14/15 and servo CH8 are spare (former tipper outputs).

## Recovery and operator calibration

There is **no local latched tipper E-stop**. STOP de-energizes active
outputs and permits operator recovery, rather than preventing the jog
needed to return the tipper to the start position. The existing upstream
ESTOP/REARM serial vocabulary remains compatible but is non-latching
within this tipper firmware.

After visual inspection of the stationary tipper, operate the timed UNLOCK,
then issue individual 200 ms `JOG CW`/`JOG CCW` commands as needed.
The operator aligns the start position and issues `MARK START`.
Jog to a visually verified 120-degree endpoint and issue `SET 120`.
A calibrated `HOME` then returns by encoder count to the marked start.
Verify alignment visually afterward. No absolute home sensor is installed.

Calibration is held in volatile controller memory. Repeating calibration
after reboot avoids assuming an absolute position from a relative encoder.
The encoder slot size corresponds to about 0.08836 inches of peripheral
wheel travel per rising edge; barrel angular motion requires mechanical
calibration rather than assuming a wheel-to-drum ratio.

The 500 ms communications watchdog, short jog duration, encoder-stall
timeout and stop motor commands remain implemented as motion safeguards.
Firmware does **not** infer a lock sensor where none exists.

## Yard and Pi IO

No GPIO outputs are reserved on the Raspberry Pi. Sensor and motion-board
I/O is on external controllers and expanders. No yard relay control signals
are currently assigned; the yard retains a logical three-track model,
with stalls 1A/1B sharing Track 1. MCP23017 GPB5/GPB6/GPB7 remain spare.

## Verification status

Changes are source-level; the code has not been flashed or bench-tested
in this chat. Compile/test and verify relay driver wiring before energizing
any equipment. The logical yard configuration does not imply active relay
control or installed signal hardware.
