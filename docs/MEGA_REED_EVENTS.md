# Mega reed input event handler

The Mega's 28 reed switches are D14-D41, grouped A-H (common,
straight, divergent), followed by mine, farm, ski, town. Active-low reed
contacts use INPUT_PULLUP Firmata mode `u`.

`MegaReedReader` binds all 28 pin callbacks when explicitly started
on a commissioned Mega. Call `poll()` at approximately 10ms intervals.
The reader retains raw edges, debounces for 15ms, reports CLOSE/OPEN
events with car-pulse counts, and fails on queue overflow. The first
observed stable state is a baseline and not an invented train passage.

The Pi `Dispatcher.handle_reed_event` records current states, counts and
recent events and forwards turnout reeds into the automatic-return
tracker. This handler NEVER calls confirm_tail_clear itself: train count
and final rear-of-consist verification must come from the tracking
layer separately. The auto-return tracker also requires verified
interlocks, route release, healthy controller state and the full 1000ms
OPEN window before permitting relay restoration.

This is a staged, opt-in implementation. No runtime currently opens the
Mega or polls it automatically, and the migration stays disabled in
`config/firmata_layout.yaml`. Hardware pulse timing and callback
reliability need bench validation.
