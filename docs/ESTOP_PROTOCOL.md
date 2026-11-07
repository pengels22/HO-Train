# Controller / XIAO emergency stop contract

The dispatcher must set all requested locomotive speeds to **zero immediately**
when E-Stop is activated. The hardware command runtime must call
`EmergencyStop.activate()` and stop submitting all queued movement commands.

The sender broadcasts the existing 12-byte `Command` frame to
`10.77.0.255:4210`, using:
- train_id = 255 (all trains)
- flags = 0x80 (ESTOP)
- speed = 0 (no deceleration ramp)
- target = 0
- incrementing 16-bit sequence number + existing CRC16
- immediate first frame; 100 ms repeated frames while latched

There is **no remote clear packet** in this protocol revision. On clearing the
controller latch, the sender stops repeated ESTOP frames but remains disarmed.
After inspecting the locomotive's status and interlocks, the operator must
explicitly rearm. The XIAO must also require its **own explicit reset/rearm**;
the controller cannot assume the locomotive has cleared its local latch.

## Locomotive firmware requirements

1. Recognize `train_id=255, flags&0x80` as emergency stop, after frame CRC checks.
2. Set PWM/motor drive to zero **before** normal command dispatch and latch E-Stop.
3. Ignore ordinary throttle commands while locally latched, including stale packets.
4. Keep the existing 500 ms no-command watchdog: zero output and fault on timeout.
5. Loss of Wi-Fi or UDP is not a signal to clear E-Stop.
6. After manual clear, require an explicit local rearm handshake/status confirmation
   before allowing nonzero speed. Never resume cached target speed.
7. Report latch and communication state to the controller when telemetry is added.

## Integration caution

This commit provides the command packet + repeating sender + tests. It does
**not** connect to any running physical hardware, change the simulation server,
or implement ESP32 firmware. The current simulator must remain network-silent.
The eventual hardware control service must funnel *every* motion packet through
`send_motion` (never a second unsafeguarded socket) and call
`activate` on every global stop or safety fault, not only the UI E-Stop.

A UDP broadcast is best-effort. Local watchdogs and physical power-cut
provisions remain important; a network-only E-Stop is not a safety-rated stop.
