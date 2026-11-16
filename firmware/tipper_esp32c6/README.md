# Dedicated XIAO ESP32-C6 rotary tipper

The XIAO exclusively controls the rotary tipper; no tipper sensor, motor,
decoupler, or lock uses Raspberry Pi GPIO.

Pin map (GPIO):
- D2/2 Hall Front, D3/21 Hall Back, D4/22 Hall Clear (car magnets; active low)
- D5/23 optical encoder, 40 slots, wheel diameter 1.125 in
- D6/16 and D7/17 rotary motor
- D8/19 and D9/20 timed 800 ms lock motor (no lock-position sensor)
- **D10/18 magnetic decoupler relay, active LOW**, pulse 250 ms

Locomotive destination-identification IR is not part of tipper control.
The encoder optical sensor measures tipper movement, not railcar clearance.

## Operator calibration and recovery

No latched E-stop is implemented on the tipper. `STOP` immediately stops
motion and turns off the decoupler; upstream `ESTOP`/`REARM` commands are
accepted for compatibility but are non-latching local stops.

The installed lock is actuated by an 800 ms motor pulse and is tracked by
software; there is no additional lock-position feedback.

From a visually safe, stationary tipper, use `STOP`, `UNLOCK`, and
`JOG CW`/`JOG CCW` to reposition using **bounded 200 ms jogs at PWM 80**.
No angular calibration is required to jog. Once the rails are precisely
aligned at the actual start position, issue `MARK START`. Jog to the
physically confirmed 120° dump angle and issue `SET 120`. These commands
calibrate the signed encoder count in RAM (not preserved across a reboot).
`HOME` subsequently reverses to the operator-marked encoder position.
After returning, visually verify rail alignment and use jog correction if
necessary. There is no physical angular home sensor.

Full automatic `ROTATE` still requires a calibrated 120° encoder count,
a marked start, the installed timed unlock and the configured Hall train
position interlock. A 500 ms communications watchdog stops any active
outputs; timed jog stops after 200 ms, with independent stalled-encoder
and rotation-timeout handling for counted movement.

The D10 relay is active LOW: HIGH is OFF, LOW is ON. The XIAO pin is only
a logic control signal; use appropriate coil driver, supply and flyback
suppression. Firmware initializes the pin inactive before setting OUTPUT.

The current source is not evidence of an installed firmware image.
Compile and bench-verify the XIAO build and wiring before operating a train.
