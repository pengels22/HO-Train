# Deployment

Install Raspberry Pi OS, Python 3.11+, clone the repository, create a virtual environment, install the package, and review `config/hardware.yaml`, `config/yard_power.yaml`, and the wiring PDF. Hardware mode is the deployment target but remains OFF/DISARMED until the physical E-Stop, power rails, fuses, I2C levels, relays, and controller links have been bench-verified. Use `--mode simulation` only for developer testing.

Controller registration is fixed by architecture: locomotive IDs 1-4 use
`m5_atom_echo` over UDP; `/dev/serial/by-id/ho-turntable` is the dedicated XIAO
ESP32-C6 turntable controller; and `/dev/serial/by-id/ho-tipper` is the
dedicated XIAO ESP32-C6 rotary tipper controller. Replace only the explicit
placeholder paths/addresses after wiring validation; do not substitute a XIAO
locomotive controller or reuse an accessory port for a locomotive.
