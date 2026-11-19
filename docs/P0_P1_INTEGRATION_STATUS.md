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

USB accessory registration lives under `controller_transport`. The physical emergency-stop GPIO monitor has been removed. Dispatcher stop, individual STOP, motion rearm, watchdogs, and accessory interlocks remain active. The 0x80 wire flag remains for flashed locomotive protocol compatibility.

## Dispatcher and yard

`run_cycle_once` selects an eligible automatic train, reserves a conservative
route, arms the next checkpoint, and exposes the cycle state machine. Actual
movement is delegated to an injected approved adapter; no hardware movement is
issued without that adapter and physical/controller verification. Checkpoint
events advance the route, and only confirmed last-car clearance releases a
zone. Yard power exposes requested, commanded, and verified states separately;
all three physical sections remain unassigned and unverified, with defaults
off.

## Verification

- Python regression suite: 112 passed.
- JavaScript syntax check: passed.
- Arduino CLI compile-only checks passed for the M5 Atom locomotive, XIAO
  ESP32-C6 locomotive variant, XIAO turntable, and XIAO rotary tipper.
- Physical wiring, GPIO assignments not marked verified, sensor alignment,
  network telemetry, and USB serial identities remain hardware-dependent and
  still require bench verification.
