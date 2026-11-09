# IR protocol

Frames are `HR`, version, train ID, status/direction, target, speed magnitude, and CRC-8. Direction is status bit 0. Carrier and timing are configurable and must be validated against the selected receiver.

The M5 firmware now schedules this frame through the GPIO23 38 kHz carrier
without blocking its UDP loop or watchdog. The symbol width remains the
explicit `IR_SYMBOL_US` build setting because this document does not define a
receiver-validated symbol timing; it must be calibrated before physical use.
