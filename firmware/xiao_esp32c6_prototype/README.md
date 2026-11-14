# XIAO ESP32-C6 accessory prototype

`locomotive_esp32.ino` is retained as an uncommissioned prototype and is not a
locomotive controller assignment. The finalized locomotive fleet uses M5 Atom
Echo controllers. The XIAO ESP32-C6 is assigned to the dedicated turntable
controllers implemented by `firmware/turntable_esp32c6/turntable_esp32c6.ino`
and `firmware/tipper_esp32c6/tipper_esp32c6.ino`.

The motor-driver mapping, Wi-Fi credentials, and local rearm-button pin remain
placeholders. Set and validate them before an explicitly enabled bench build.
The simulation dashboard does not compile or run this sketch and never sends
physical UDP traffic.
