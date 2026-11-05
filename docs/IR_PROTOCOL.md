# IR protocol

Frames are `HR`, version, train ID, status/direction, target, speed magnitude, and CRC-8. Direction is status bit 0. Carrier and timing are configurable and must be validated against the selected receiver.
