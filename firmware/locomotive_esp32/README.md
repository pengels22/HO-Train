# XIAO ESP32-C6 turntable controller

`locomotive_esp32.ino` is retained as an uncommissioned prototype and is not a
locomotive controller assignment. The finalized locomotive fleet uses M5 Atom
Echo controllers. The XIAO ESP32-C6 is assigned to the dedicated turntable
controller implemented by `turntable_esp32c6.ino`.

The motor-driver mapping, Wi-Fi credentials, and local rearm-button pin remain
placeholders. Set and validate them before an explicitly enabled bench build.
The simulation dashboard does not compile or run this sketch and never sends
physical UDP traffic.
