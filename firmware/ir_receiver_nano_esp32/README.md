# Arduino Nano ESP32 production IR receiver

Receive-only 14-channel target for `arduino:esp32:nano_nora`. It decodes the
locomotive's 1–4 flash beacon, takes three frames per input, reports the
majority train ID as newline-delimited JSON at 115200 baud, and reports
`no_train` when clear. It configures no actuator outputs. Pin assignments must
still be electrically verified during commissioning; the single-D2 bench
instrument remains in `ir_receiver_nano_esp32_bench`.

```text
arduino-cli compile --fqbn arduino:esp32:nano_nora firmware/ir_receiver_nano_esp32
```
