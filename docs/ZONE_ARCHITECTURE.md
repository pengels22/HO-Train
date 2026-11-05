# Zone architecture

The railroad has 15 logical operating zones: three each for Ski, Farm, Underground, Mine, and Main. Zones are control and tracking units, not electrical power districts; the constant 12V distribution is unchanged.

`config/zones.yaml` defines identity, railway/color, neighboring zones, elevation, checkpoints, Hall sensors, turnouts, and verification status. `config/zone_boundaries.yaml` stores editable normalized overlay polygons independently of image pixel dimensions. `config/track_topology.yaml` is the future authoritative segment graph and is currently marked unverified.

The engine is conservative: proposed/unverified zones cannot be reserved for hardware-mode routing, ambiguous Hall/IR evidence produces UNKNOWN, and an IR sighting does not clear the previous zone until consist clearance is confirmed.
