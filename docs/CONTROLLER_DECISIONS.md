# HO Controller Decisions

The design has four locomotives, fifteen operating zones, eleven overhead IR checkpoints, one USB Nano decoder, and three yard power relays. Yard Track 1 supplies both stalls 1A and 1B.

The finalized hardware architecture is: Raspberry Pi 4B central dispatcher and
I/O controller; four M5 Atom Echo locomotive controllers; one dedicated XIAO
ESP32-C6 turntable controller; and one dedicated XIAO ESP32-C6 rotary tipper
controller. Hardware remains disarmed until outputs and safety interlocks are
commissioned.
