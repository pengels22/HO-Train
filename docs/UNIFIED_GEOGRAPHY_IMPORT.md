# Unified railroad geography (Nov 6, 2026)

Source: user-exported `HO_Train_Unified_Geography.json` from the standalone unified layout editor. The entire set of 89 centerline segments and their coordinate points is preserved exactly in `config/unified_geography.json`.

- Coordinate system: original-mockup 739 × 593. Use the matching source image, not the previous 752 × 602 crop, and never reapply the offset.
- 15 zone boundary pairs and 11 IR receivers are carried over from the user's exported JSON, retaining their per-item verification states.
- Existing 25 Hall sensors (H01–H25) are user-verified, including H01 whose checkbox was missed.
- Original 89 geometry paths: **visually aligned/approved by the user**. This does **not** imply segment connectivity, turntable stopping, safe routes, or simulation paths are verified.
- Eight powered turnouts A–H; G and H default **straight**.
- H is new and connects to the short UND-4 turntable branch. H's exact position and its straight/common graph edges have not yet been captured in the exported JSON; do not fabricate them. Three feedback sensors H26/H27/H28 remain **unplaced** until those coordinates are supplied.
- Pin assignments **MCP2 GPB2/GPB3/GPB4** are proposed for H. Do NOT use GPA6, GPA7 or GPB0 because those are already allocated to Mine/Farm/Ski station feedback in `config/sensors.yaml`.
- UND-4 needs no additional dedicated occupancy Hall sensor. The turntable rotates 180° and reverses to home. The three sensors at H only prove turnout-position state; they do not establish locomotive position or turntable home/rotation completion.

## Codex integration requirements

1. Pull the new config and preserve local unpushed work. Do not reset/overwrite local branches.
2. Use `config/unified_geography.json` as the authoritative overlay data for zones, IRs, turnouts and Hall sensors. Preserve IDs and coordinates. Do not recreate geometry from images.
3. Render on the matching native mockup image, or compute exactly one tested transform to another image.
4. Map JMRI segment IDs and explicit junction connections. The track's operating graph and turnout H common/straight mapping remain unverified; no automated dispatch until validated.
5. Update dashboard, sensor config and route simulation for turnout H and UND-4 with safe stopping interlocks. No live hardware outputs.
6. Add tests for 89 unchanged geometry segments, 15 zones, 11 IRs, 8 turnouts, 28 Hall IDs, no pin conflicts, G/H default straight, and fail-closed turntable dispatch.
