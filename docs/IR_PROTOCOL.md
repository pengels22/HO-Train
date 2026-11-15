# IR protocol

Frames are eight bytes, sent least-significant bit first:

`HR`, version, train ID, status/direction, target, speed magnitude, and CRC-8.

Direction is status bit 0. The M5 transmits through GPIO23 using a 38 kHz
carrier and a pulse-distance envelope suitable for a demodulating IR receiver:

- Each mark is a 2 ms carrier burst.
- Four synchronization marks use a 4 ms gap (about 6 ms between pulse starts).
- The first data mark follows a 20 ms separator plus its bit gap: about 28 ms
  between pulse starts for zero, or 34 ms for one.
- Later bits use about 8 ms between pulse starts for zero, or 14 ms for one.
- There are 64 data bits, followed by 100 ms before the next frame.

The M5 schedules the frame without blocking its UDP loop, communications
watchdog, or locomotive safety handling. The Nano bench receiver tolerates
normal demodulator timing variation and validates the `HR` header and CRC
before reporting a decoded train event. These timings are now the deployed
protocol; physical optical range and alignment still require bench validation.
