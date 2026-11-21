# Mega 2560 / classic Nano Firmata migration (proposed)

This branch is a **non-energizing first pass**. It adds a declarative pinout and
a lazy pyFirmata2 adapter. No startup path imports/opens this adapter, and
`config/firmata_layout.yaml` is disabled by default. It does **not** replace
the existing Pi MCP/PCA hardware runtime yet.

* Mega D2-D11: reversible PWM motor channels M2/M4-M7.
* Mega D46-D49: bidirectional full-speed M1/M3 via existing DRV8833 drivers.
* Mega D14-D37: 24 reed inputs, groups A-H (common, straight, diverging).
* Mega D38-D41: mine, farm, ski, town destination reeds.
* Mega D44-D45: two crossing gate servos.
* Classic Nano D2-D9: eight active-low turnout **direction select** relays.
* Classic Nano D10-D12: three independent active-low yard track power relays.
* Classic Nano D13: spare. The safe turnout coil pulse-enable design is **not commissioned**.
* Nano ESP32: existing custom USB IR decoder, with 3 proposed station receiver
  locations appended to the existing 11. A0-A2 require physical pin validation.
* Turntable and tipper XIAO C6 retain their existing local control and USB paths.

**Warning:** Arduino internal pull-ups cannot hold active-low relay signals
safe while the MCU is unpowered or reset. StandardFirmata does not guarantee
high-before-output relay initialization or a USB-disconnect watchdog. Module
hardware and boot transients must be bench-verified before energizing relay banks.

Eight turnout relays select solenoid direction but do not provide an independent
pulse limit. Never energize turnout coils until a safe pulse scheme is designed,
validated and wired. Train-detection reeds are not turnout-alignment feedback.

The topology keeps H's unsurveyed straight/common links as TBD rather than
inventing route geometry. H is a physical powered turnout and is deliberately
not eligible for verified routing until those links are surveyed.

Install `pyfirmata2` only when bench-testing the optional adapter. Continue to
run all existing dispatch and controller tests with outputs disabled.
