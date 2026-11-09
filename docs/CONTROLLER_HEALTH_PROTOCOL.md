# Controller health and recovery protocol

The existing 12-byte `HC` motor command remains unchanged. Locomotive
telemetry uses a separate versioned `HT` packet whose payload is compact JSON:

```json
{"version":1,"id":1,"state":"ARMED","estop":false,
 "communication_fault":false,"armed":true,"speed":0,
 "sequence":7,"session":"boot-1","uptime_ms":100}
```

The dispatcher accepts telemetry only for configured locomotive IDs, tracks
sequence/session/freshness, and requires an armed, non-faulted, non-E-Stop
status before motion rearm. Missing or stale required telemetry invokes the
same global safety stop path as a failed required USB controller.

In explicit hardware mode the Pi listens for these `HT` telemetry datagrams on
UDP port `4211`; simulation mode does not bind the telemetry socket.

Registered USB controllers use newline commands. `ESTOP\n` remains an
immediate, acknowledgement-independent stop. Recovery uses `REARM AUTH\n`
and requires a JSON response identifying the controller with `estop=false`,
`motor=false`, `track_power=false`, and no reported fault. `STATUS\n` is the
100 ms heartbeat; a heartbeat cannot clear a latch or authorize motion.

Simulation creates an empty logical registry only. It does not open GPIO,
serial, UDP, motor, relay, or track-power transports.
