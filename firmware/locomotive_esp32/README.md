# Locomotive ESP32 prototype

`locomotive_esp32.ino` implements the UDP command frame and the fail-closed
E-Stop behavior for the XIAO ESP32-C6 mock locomotive. Broadcast train ID 255
with flag `0x80` immediately latches the motor at zero. Packet silence never
clears that latch; the 500 ms watchdog independently forces zero output.

The motor-driver mapping, Wi-Fi credentials, and local rearm-button pin remain
placeholders. Set and validate them before an explicitly enabled bench build.
The simulation dashboard does not compile or run this sketch and never sends
physical UDP traffic.
