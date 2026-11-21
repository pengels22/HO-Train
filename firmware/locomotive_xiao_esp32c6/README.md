# XIAO ESP32-C6 locomotive controller variant

This is a board-specific variant of the existing M5 Atom locomotive firmware.
It preserves the same UDP command packet, explicit rearm/E-Stop behavior,
communications watchdog, telemetry JSON, and 38 kHz IR beacon protocol. The
M5 sketch remains the primary production locomotive target and is not replaced.

## Pin map

| XIAO board pin | ESP32-C6 GPIO | Function |
|---|---:|---|
| D7 | 17 | Motor driver IN1 / forward PWM |
| D8 | 19 | Motor driver IN2 / reverse PWM |
| D9 | 20 | IR transmitter driver |

D7/GPIO17 and D8/GPIO19 support the Arduino-ESP32 LEDC-backed `analogWrite`
path used by the shared firmware. D9/GPIO20 is a digital carrier output and is
configured with the same 38 kHz LEDC carrier as the M5 target.

This mapping is a separate locomotive harness. It must not be installed on the
dedicated tipper XIAO, where D8/D9 are the gripper lock outputs.

## Compile

```sh
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 \
  --build-property 'build.extra_flags=-DLOCOMOTIVE_ID=1' \
  firmware/locomotive_xiao_esp32c6
```

Change only `LOCOMOTIVE_ID` for another independent locomotive. Supply Wi-Fi
credentials through an untracked `wifi_credentials.h`; no credentials belong
in this sketch or in the repository. Telemetry targets Lab 1 at
`192.168.20.36:4211` by default; define `HO_CONTROLLER_IP` at build time for
another dispatcher address.
