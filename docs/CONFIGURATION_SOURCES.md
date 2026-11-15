# Configuration sources

The imported unified layout is authoritative for geography and marker
coordinates. `config/unified_geography.json` is loaded by the geography API;
the imported track graph remains unverified until the physical review gate is
completed.

`config/simulation_paths.yaml` is the simulation adapter. It may contain only
surveyed paths marked `verified: true`; an empty or unverified file prevents
simulation motion. `config/track_topology.yaml` is a legacy topology note and
is not used to generate or replace the imported geometry.

Turnout interlocking uses the active set A–H from
`railroad/routing/interlocking.py`; the physical layout's passive splitters
are not commandable turnouts. Turntable hardware assignments and pulse timing
are documented in `config/turntable.yaml`. Simulation remains the default and
all hardware output configuration is disabled unless explicitly supplied by a
validated deployment.

The I/O documentation's “passive splitters” (`P1`–`P3`) are physical track
branches from the imported JMRI layout, not electrical I/O points and not
powered turnouts. They therefore do not appear as GPIO or relay assignments.
