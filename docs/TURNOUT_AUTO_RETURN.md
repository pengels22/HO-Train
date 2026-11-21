# Turnout return-to-standard (Firmata migration branch)

The Pi dispatcher owns the clearance timer. Mega reports debounced reed edges,
Nano Classic receives relay direction commands. The configuration is still
**not armed**, no USB ports are opened automatically, and auto-return must be
explicitly attached to a commissioned relay writer.

For all A-H, relay HIGH/OFF selects NC (standard) and LOW/ON selects NO
(alternate). A: NC=diverging, NO=straight. B-H: NC=straight, NO=diverging.
All relay inputs now have external pull-ups; startup electrical behavior should
still be bench verified. Relay contacts maintain their selected state.

When an alternate route is commanded, the tracker waits until that exit's reed
has been CLOSED at least once, then continuously OPEN for at least 1,000ms.
The dispatcher must separately confirm rear-of-consist clearance (magnetic
strip on every car). Every re-closure resets the timer and tail confirmation.
A blocked/reserved turnout, occupancy, unavailable status or USB disconnect
prevents automatic return. No action on common/other-exit reed events.

In the current migration, the dispatcher provides an opt-in
`enable_turnout_auto_return()`, `turnout_reed_event()`,
`turnout_tail_confirmed()` and `poll_turnout_returns()` API.
**The USB sensor ingestion and authoritative route/occupancy-event adapter
have not yet been connected.** Until then no automatic switch restoration
runs in production. Do not call poll with guessed empty interlock sets.

Only relay-commanded alignment is known; train reeds do not verify point
position. Turnout H's physical common/straight track links still require survey.
