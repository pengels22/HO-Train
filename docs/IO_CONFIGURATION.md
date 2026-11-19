# Authoritative I/O configuration

The Raspberry Pi `config/io_config.csv` file is the editable source of truth
for controller channel metadata. The dashboard reads and writes it through
`/api/io-config`; browser local storage is only a presentation cache.

The physical inventory is fixed by `config/hardware.yaml` and is expanded into
the following controller views:

| Controller | Physical device | Channels |
| --- | --- | --- |
| Motion Controller 1 | PCA9685 `0x40` (`motor_1`) | 0–15 |
| Servo Controller | PCA9685 `0x41` (`servo`) | 0–15 |
| Input Controller 1 | MCP23017 `0x20` (`sensors_1`) | GPA0–GPB7 |
| Input Controller 2 | MCP23017 `0x21` (`sensors_2`) | GPA0–GPB7 |
| IR Sensor Configuration | Nano ESP USB receiver | CH1–CH12 |

Motor channels may be `Motor` or `Unassigned`; servo channels may be `Servo` or
`Unassigned`. Input and
IR channels are digital inputs; their bias is either `Pull-up (internal)` or
`No bias`. Turntable and rotary tipper channels are deliberately absent from
these Pi controller views because those are standalone USB controllers.

The Pi keeps the physical board identity (`pca9685`, address, and channel)
separate from the editable assignment. Existing `motion2` CSV rows are
migrated to the servo controller; incompatible motor assignments are preserved
as `Unassigned` with a migration warning. The first migration creates
`config/io_config.csv.bak` so the original mapping remains recoverable.

The initial motion mapping reserves PCA9685 channels 0 and 1 as the paired
`1A`/`1B` motor controls. All other motion channels are unassigned until
commissioned. Saving metadata validates the complete row set and reloads the
same physical mapping into `HardwareRegistry`; it does not energize an output.

In hardware mode, declared I²C devices are opened through the injected bus
adapter. MCP inputs are configured with pull-ups by default and PCA9685 output
latches are cleared during initialization and shutdown. A missing Linux I²C
backend is reported as a runtime hardware fault; it is never silently replaced
with simulation.
