# Arduino Nano ESP32 bench IR receiver

This is a non-actuating bench receiver for the test track. Wire one
demodulated IR receiver output to Arduino Nano ESP32 `D2`, with the receiver
output idle HIGH and active LOW. USB serial runs at 115200 baud.

The device reports the selected logical endpoint in the same JSON event shape
used by the Pi IR parser. Since one simple receiver cannot decode the M5
beacon's train identity, select the test identity explicitly:

```text
SET ENDPOINT mine_station
SET TRAIN 1
STATUS
```

Settings are retained in ESP32 non-volatile storage. `LIST` prints all
supported endpoint IDs. A falling/active sensor edge emits one event such as:

```json
{"receiver":"Mine Station","endpoint_id":"mine_station","train_id":1,"speed":0,"source":"bench_nano_esp32"}
```

The receiver detects an M5 carrier burst rather than waiting for a sustained
LOW level: the M5 frame uses 1 ms symbols and the demodulated output returns
HIGH between carrier symbols. A burst is accepted after 1 ms of carrier and
closed after an 8 ms idle gap, with an 80 ms minimum event interval.

This sketch does not drive motors, relays, track power, or locomotives. It is
separate from the production 11-channel Nano diagnostic sketch.

Compile with Arduino CLI using the Nano ESP32 board definition:

```sh
arduino-cli compile --fqbn arduino:esp32:nano_nora firmware/ir_receiver_nano_esp32_bench
```
