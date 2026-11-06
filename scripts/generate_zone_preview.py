#!/usr/bin/env python3
"""Generate a non-authoritative SVG zone overlay over the preserved layout image."""
from pathlib import Path
import html
import yaml

ROOT = Path(__file__).resolve().parents[1]
zones = yaml.safe_load((ROOT / "config/zones.yaml").read_text())["zones"]
boundaries = yaml.safe_load((ROOT / "config/zone_boundaries.yaml").read_text())["boundaries"]
colors = {"white": "#e8eef2", "yellow": "#ffe02b", "blue": "#5674ff", "red": "#ff3a3a", "gray": "#aab0b8"}
width, height = 1559, 1009
parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<image href="railroad-layout.png" width="100%" height="100%"/>']
for zone in zones:
    item = boundaries[zone["id"]]
    pts = " ".join(f"{x*width:.1f},{y*height:.1f}" for x, y in item["polygon"])
    color = colors[zone["color"]]
    cx = sum(p[0] for p in item["polygon"]) / len(item["polygon"]) * width
    cy = sum(p[1] for p in item["polygon"]) / len(item["polygon"]) * height
    label = html.escape(zone["id"])
    parts.append(f'<polygon points="{pts}" fill="{color}" fill-opacity="0.20" stroke="{color}" stroke-width="4" stroke-dasharray="10 6"/>')
    parts.append(f'<g><rect x="{cx-38:.1f}" y="{cy-16:.1f}" width="76" height="28" rx="5" fill="#101820" fill-opacity="0.88"/><text x="{cx:.1f}" y="{cy+4:.1f}" text-anchor="middle" fill="white" font-family="sans-serif" font-size="16" font-weight="bold">{label}</text></g>')
parts.append('<text x="24" y="38" fill="white" font-family="sans-serif" font-size="22" font-weight="bold" stroke="#101820" stroke-width="5" paint-order="stroke">PROPOSED ZONE OVERLAY — UNVERIFIED</text></svg>')
(ROOT / "assets/layout/zone-overlay-preview.svg").write_text("\n".join(parts))
print(ROOT / "assets/layout/zone-overlay-preview.svg")
