# Current controller decisions

Authoritative design: [Hardware decisions](HARDWARE_DECISIONS.md), [Pinout](HARDWARE_PINOUT.md), and [Control tray](CONTROL_TRAY.md).

Raspberry Pi 4B runs dispatcher and dashboard. Mega 2560 and Nano Classic use USB Firmata. The Nano ESP32 is a dedicated USB IR decoder (14 planned channels, one physical bench channel currently implemented). Separate XIAO C6 controllers run the turntable and tipper. Locomotives use wireless UDP; both M5 Atom Echo and XIAO C6 variants are supported. No Pi I2C railroad I/O or dedicated physical emergency-stop subsystem.

Eight powered turnouts A-H, three passive P1-P3, three yard power circuits (Track 1 shared by 1A/1B), seven accessory motors, two crossing servos, 28 Mega reed inputs. A standard diverging; B-H standard straight. Active-low maintained relay selector; NC standard. Return after verified consist clearance and 1000ms continuous OPEN, no occupation or route hold. See hardware decisions for commissioning gaps.
