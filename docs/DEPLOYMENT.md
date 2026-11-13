# Deployment

Install Raspberry Pi OS, Python 3.11+, clone the repository, create a virtual environment, install the package, and review `config/hardware.yaml`, `config/yard_power.yaml`, and the wiring PDF. Hardware mode is the deployment target but remains OFF/DISARMED until the physical E-Stop, power rails, fuses, I2C levels, relays, and controller links have been bench-verified. Use `--mode simulation` only for developer testing.

Controller registration is fixed by architecture: locomotive IDs 1-4 use
`m5_atom_echo` over UDP; `/dev/serial/by-id/ho-turntable` is the dedicated XIAO
ESP32-C6 turntable controller; and `/dev/serial/by-id/ho-tipper` is the
dedicated XIAO ESP32-C6 rotary tipper controller. Replace only the explicit
placeholder paths/addresses after wiring validation; do not substitute a XIAO
locomotive controller or reuse an accessory port for a locomotive.

## Tipper USB commissioning

The dedicated tipper C6 was compiled and flashed successfully on 2026-11-13.
The verified USB identity is:

| Field | Value |
|---|---|
| Board | Seeed XIAO ESP32-C6 (`esp32:esp32:XIAO_ESP32C6`) |
| Chip | ESP32-C6FH4, 4 MB flash |
| USB serial number / MAC | `90:64:9B:AA:64:AC` |
| Commissioning host port | `/dev/cu.usbmodem14401` (transient macOS name) |
| Pi service path | `/dev/serial/by-id/ho-tipper` (pending Pi-side udev verification) |
| Serial speed | `115200` baud |

On the Raspberry Pi, connect the board and use `udevadm info`/`udevadm test`
to match the USB serial number before installing the `ho-tipper` symlink. Do
not assume the macOS port name is persistent. The tipper firmware currently
has no finalized GPIO map, so its motor, lock, and decoupler outputs remain
disabled and it must not be rearmed during commissioning.
