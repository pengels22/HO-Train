# Hardware decision baseline — 2026-11-21

Current architecture and physical layout: CONTROL_TRAY.md and HARDWARE_PINOUT.md. These supersede older I2C documents and the historical wiring PDF.

Confirmed: Mega USB identity recorded and StandardFirmataPlus 2.5.9 flashed; Nano Classic identity pending. 28 reeds, seven DRV8833 motors (M1/M3 full speed, other five PWM), two gates, 8 powered A-H and 3 passive splitters, 12 relay channels (11 assigned). External relay pull-ups. 12V turnout maintained selectors: NC standard (A diverging, others straight), NO alternate. Relay remains selected until new command or confirmed rear-clear plus 1000ms continuously OPEN with route/occupancy interlocks. No arbitrary release timeout. Continuous solenoid current rating/internal cutoff still requires verification before powering coils. Train reeds do not prove physical alignment.

Open decisions: H common/straight topology; per-consist train counts and direction-aware exit matching for live auto-return; Nano Classic USB identity and transient-free startup; production 14-input IR decoder and 3.3V electrical compatibility; controller reconnect/reconciliation; real motor/gate commissioning; turntable 6V TT timed 180-degree rotation, endpoint reeds, physical stops, requested 10% holding duty and polarity automation (timing and thermal tests pending); tipper encoder calibration, front/rear IR requirement and restraint feedback; decoupler supply; fuse sizing; DIN terminal schedule; HID firmware/runtime merge. Do not invent values or report these as implemented.

No physical emergency-stop subsystem. Existing local watchdog and dispatcher stop semantics retained. Only locomotives wireless.
