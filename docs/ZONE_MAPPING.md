# Zone mapping proposal

The source image is preserved at `assets/layout/railroad-layout.png`; its colored lines are used only as a visual reference. The dashed overlay in `assets/layout/zone-overlay-preview.svg` shows the initial proposal.

- White: `SKI-1` through `SKI-3`
- Yellow: `FARM-1` through `FARM-3`
- Blue: `UND-1` through `UND-3`
- Red: `MINE-1` through `MINE-3`
- Gray: `MAIN-1` through `MAIN-3`

All polygons are provisional. The image does not establish rail connectivity at visual crossings, and no crossing has been promoted to a machine-authoritative connection. Yard receivers remain location-specific and preserve the three-track/four-position arrangement: Track 1 has 1A and 1B; Tracks 2 and 3 have Stall 2 and Stall 3.

Edit normalized polygons in `config/zone_boundaries.yaml`, then regenerate the preview with:

```sh
.venv/bin/python scripts/generate_zone_preview.py
```
