# Authoritative I/O configuration

The Raspberry Pi `config/io_config.csv` file is the editable source of truth
for controller channel metadata. The dashboard reads and writes it through
`/api/io-config`; browser local storage is only a presentation cache.

The physical inventory is fixed by `config/hardware.yaml` and is expanded into
the following controller views:

| Controller | Physical device | Channels |
| --- | --- | --- |
| Arduino Mega 2560 outputs | USB Firmata | D2–D11, D44–D49 |
| Arduino Mega 2560 reed inputs | USB Firmata | D14–D41 |
| Arduino Nano Classic relay outputs | USB Firmata | D2–D12 |
| Arduino Nano ESP32 IR | Dedicated USB serial protocol | CH1–CH14 |

Motor channels may be `Motor` or `Unassigned`; servo channels may be `Servo` or
`Unassigned`. Input and
IR channels are digital inputs; their bias is either `Pull-up (internal)` or
`No bias`. Turntable and rotary tipper channels are deliberately absent from
these Pi controller views because those are standalone USB controllers.

Turnouts A-H are three-wire SPDT loads, not servos. Their external +12 V
common is switched by a relay: NC is straight and NO is diverging. The logical
common/straight/divergent reed inputs are assigned below; physical reed
installation and polarity remain commissioning items. The dispatcher records
the commanded relay state until those inputs are validated.
Relay control uses active-low Nano Classic outputs: LOW selects the requested
relay state and HIGH is the safe idle state, as mapped in
`config/firmata_layout.yaml`. The Pi never sources the external turnout +12 V
directly.

The logical relay order is A-H on Nano pins D2-D9, followed by yard relays on
D10-D12. Each turnout has three Mega reed inputs in common, straight,
divergent order. The two gate servos use Mega pins D44 and D45.

The two genuine servos, Farm gates and Town gates, use Mega pins D44 and D45
with the same simple profile:
home at 90°, actuate to 0°, then return to 90°.

The Pi keeps the physical Firmata board identity and pin separate from the
editable assignment. Legacy CSV rows remain recoverable during migration but
are not used to activate I²C hardware.

Saving metadata validates the complete USB row set and reloads the same
physical mapping into `HardwareRegistry`; it does not energize an output.

In hardware mode, Firmata devices are opened only after explicit commissioning
and verified USB paths. Mega motor outputs initialize to zero, crossing servos
to 90°, and Nano relay outputs HIGH. A missing USB backend is reported as a
runtime hardware fault; it is never silently replaced with simulation.
