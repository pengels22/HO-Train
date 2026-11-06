# Pass 2 implementation plan

1. Preserve Pass 1 hardware assignments and add a typed zone model around the existing `Section` and `TrackGraph` abstractions.
2. Add 15 configurable zones, boundaries, topology, and validation. All proposed geometry remains unverified until the RailModeller image is supplied and surveyed.
3. Add conservative zone occupancy/reservation transitions and locomotive zone state without releasing a previous zone on IR identification alone.
4. Add zone-aware route conflict tests and a read-only dashboard endpoint/editor data model. Live hardware routing will require validated configuration.
5. Generate a configuration-driven overlay preview that does not alter the source image; if the source image is absent, produce a clearly marked schematic preview only.

The repository currently does not contain `assets/layout/railroad-layout.png`. No physical connectivity or pixel geometry will be inferred until that asset is added.
