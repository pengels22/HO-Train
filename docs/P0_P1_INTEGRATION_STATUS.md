# P0/P1 integration status

This branch keeps the repository in its safe simulation-default state. No
board was flashed and no motor, relay, servo, or decoupler output was enabled.

## Controller inventory

- Locomotive IDs 1–4 accept either `m5_atom_echo` or `xiao_esp32_c6` without
  changing the configured type implicitly.
- The health inventory and dashboard preserve the configured type for each
  locomotive.
- Turntable, rotary tipper, and Nano IR receiver remain separate USB
  controller entries.

The `estop` YAML section is retained only as the serial registry for
controller-local STOP/watchdog propagation. There is no Raspberry Pi physical
E-stop GPIO requirement. Dispatcher global stop, individual STOP, rearm,
watchdogs, and accessory interlocks remain active.

## Dispatcher and yard

`run_cycle_once` creates a dispatcher plan only after selecting an eligible
automatic train. It does not issue motion while route, sensor, and controller
health verification are incomplete. Yard power exposes requested and verified
states separately; all three physical sections remain unassigned and
unverified, with defaults off.

## Verification

- Python regression suite: 112 passed.
- JavaScript syntax check: passed.
- Arduino CLI compile-only checks passed for the M5 Atom locomotive, XIAO
  ESP32-C6 locomotive variant, XIAO turntable, and XIAO rotary tipper.
- Physical wiring, GPIO assignments not marked verified, sensor alignment,
  network telemetry, and USB serial identities remain hardware-dependent and
  still require bench verification.
