# Dashboard

The dashboard is served by `railroad.api.server` in either simulation or hardware mode.

In hardware mode it is a dispatcher view for the four independent M5 Atom locomotive controllers, the dedicated XIAO ESP32-C6 turntable, and the dedicated XIAO ESP32-C6 rotary tipper. It displays controller connectivity, raw accessory safety/output telemetry, alignment, pin-map verification, and the dispatcher stop state. The Routes tab can assign a selected train to a selected destination through the Pi dispatcher; assignment changes dispatcher state only and does not issue a motion command. The bench rearm action only requests the existing controller handshake; it does not issue motion commands and remains subject to the accessory alignment interlock.

Simulation controls remain available in simulation mode and never drive physical outputs. Hardware mode does not use simulated locomotive positions or accessory state as a substitute for controller telemetry.
