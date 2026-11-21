# Authoritative I/O configuration

The Raspberry Pi `config/io_config.csv` file is the editable source of truth
for controller channel metadata. The dashboard reads and writes it through
`/api/io-config`; browser local storage is only a presentation cache.

The physical inventory is fixed by `config/firmata_layout.yaml` and is expanded
into the following controller views. The editor presents sixteen logical slots
per controller; slots without a physical assignment remain `Unassigned`.

| Controller | Physical device | Channels |
| --- | --- | --- |
| Motion Controller 1 (Mega outputs) | Arduino Mega 2560 / USB Firmata | 16 channels: M1–M7 pairs and D44/D45 servos |
| Motion Controller 2 (relay outputs) | Arduino Nano Classic / USB Firmata | 16 logical slots; D2–D12 assigned, D13 spare, CH14–CH16 unassigned |
| Input Controller 1 | Arduino Mega 2560 / USB Firmata | reed channels 1–16, physical D14–D29 |
| Input Controller 2 | Arduino Mega 2560 / USB Firmata | reed channels 1–12, physical D30–D41; four spare slots |
| IR Sensor Configuration | Arduino Nano ESP32 / USB serial | CH1–CH14 |

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
editable assignment. Historical CSV rows remain recoverable during migration
but are not used to activate retired hardware drivers.

The dashboard exposes editable tags and configuration/status for every row.
Output rows are limited to Motor, Relay, Servo, or Unassigned. Input rows are
digital inputs with Pull-up (internal) or No bias. Turnout tags use `As`
(straight), `Ad` (divergent), and `Ac` (common); station tags may use names
such as `Ski`, `Grain`, and `Mine`. Saving metadata validates the complete USB row set and reloads the same
physical mapping into `HardwareRegistry`; it does not energize an output.

In hardware mode, Firmata devices are opened only after explicit commissioning
and verified USB paths. Mega motor outputs initialize to zero, crossing servos
to 90°, and Nano relay outputs HIGH. A missing USB backend is reported as a
runtime hardware fault; it is never silently replaced with simulation.
