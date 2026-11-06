"""Import JMRI LayoutEditor XML without discarding its native graph IDs."""
from __future__ import annotations
from pathlib import Path
import copy
import math
import xml.etree.ElementTree as ET
import yaml

DEFAULT_SOURCE = Path("/Users/patrickengels/Downloads/dream train lauyout.xml")

def _xy(node, scale_x, scale_y, offset_x, offset_y):
    return [round(float(node.get("x", 0)) * scale_x + offset_x, 4), round(float(node.get("y", 0)) * scale_y + offset_y, 4)]

def _arc_points(start, end, degrees, flip=False, count=13):
    """Sample an arc from the XML endpoints and included angle.

    The source contains endpoints and angle but not a center; the derived
    sample is therefore retained as unverified and the source attributes are
    preserved on every segment.
    """
    x0, y0 = map(float, start); x1, y1 = map(float, end)
    chord = math.hypot(x1-x0, y1-y0)
    theta = math.radians(abs(float(degrees or 0)))
    if chord == 0 or theta == 0: return [list(start), list(end)]
    radius = chord / (2 * math.sin(theta/2))
    mx, my = (x0+x1)/2, (y0+y1)/2
    nx, ny = -(y1-y0)/chord, (x1-x0)/chord
    offset = math.sqrt(max(0.0, radius*radius-(chord/2)**2))
    sign = -1 if flip else 1
    cx, cy = mx + sign*nx*offset, my + sign*ny*offset
    a0, a1 = math.atan2(y0-cy,x0-cx), math.atan2(y1-cy,x1-cx)
    direction = 1 if sign > 0 else -1
    while direction > 0 and a1 < a0: a1 += 2*math.pi
    while direction < 0 and a1 > a0: a1 -= 2*math.pi
    return [[round(cx+radius*math.cos(a0+(a1-a0)*i/(count-1)),4), round(cy+radius*math.sin(a0+(a1-a0)*i/(count-1)),4)] for i in range(count)]

def import_jmri(source: Path, source_width=160.0, source_height=117.0, width=752.0, height=602.0, scale_x=None, scale_y=None, offset_x=None, offset_y=None) -> dict:
    root = ET.parse(source).getroot()
    layout = root.find(".//LayoutEditor")
    if layout is None: raise ValueError("JMRI LayoutEditor element not found")
    sx, sy = scale_x or 4.7383112352, scale_y or 6.3744588745
    offset_x = 33.9392882066 if offset_x is None else offset_x
    offset_y = -92.6287878788 if offset_y is None else offset_y
    points = {n.get("ident"): _xy(n, sx, sy, offset_x, offset_y) for n in layout.findall("positionablepoint")}
    turnout_points = {}
    turnouts = {}
    for n in layout.findall("layoutturnout"):
        ident=n.get("ident"); turnouts[ident]={k:n.get(k) for k in ("type","continuing","connectaname","connectbname","connectcname")}
        turnout_points[ident]=_xy({"x":n.get("xcen",0),"y":n.get("ycen",0)},sx,sy,offset_x,offset_y)
    tt = layout.find("layoutturntable")
    turntable = None
    if tt is not None:
        turntable={"id":tt.get("ident"),"center":_xy({"x":tt.get("xcen",0),"y":tt.get("ycen",0)},sx,sy,offset_x,offset_y),"radius":float(tt.get("radius",0))*sx,"rays":[]}
    junctions={k:{"type":"anchor","source_id":k} for k in points}
    junctions.update({k:{"type":"turnout","source_id":k} for k in turnout_points})
    if turntable: junctions[turntable["id"]]={"type":"turntable","source_id":turntable["id"]}
    segments={}; zero=[]
    for n in layout.findall("tracksegment"):
        sid=n.get("ident"); a=n.get("connect1name"); b=n.get("connect2name")
        def endpoint(name): return points.get(name, turnout_points.get(name, turntable["center"] if turntable and name.startswith("TUR") else None))
        p0,p1=endpoint(a),endpoint(b)
        if p0 is None or p1 is None: raise ValueError(f"{sid}: unknown endpoint {a} or {b}")
        source_attrs={k:v for k,v in n.attrib.items() if k not in {"class"}}
        if n.get("bezier") == "yes":
            cps=[]
            for cp in n.findall("./controlpoints/controlpoint"):
                cps.append(_xy(cp,sx,sy,offset_x,offset_y))
            points_out=[p0]+cps+[p1]
            kind="bezier"
        elif n.get("arc") == "yes":
            points_out=_arc_points(p0,p1,n.get("angle"),n.get("flip")=="yes")
            kind="arc"
        else:
            points_out=[p0,p1]; kind="straight"
        if a == b: zero.append(sid)
        segments[sid]={"track_path":"JMRI","source_id":sid,"source_kind":kind,"start":a,"end":b,"points":points_out,"source":source_attrs}
    for n in layout.findall("tracksegment"):
        if n.get("connect1name","").startswith("TUR") or n.get("connect2name","").startswith("TUR"):
            if turntable: turntable["rays"].append(n.get("ident"))
    connections=[{"segment_id":sid,"from":seg["start"],"to":seg["end"],"source_id":sid} for sid,seg in segments.items()]
    return {"verified":False,"coordinate_system":"clean_image_pixels","source_format":"JMRI LayoutEditor XML","source_file":source.name,"source_width":source_width,"source_height":source_height,"width":width,"height":height,"transform":{"scale_x":sx,"scale_y":sy,"offset_x":offset_x,"offset_y":offset_y,"method":"image rail-extents fit from clean background; review required"},"junctions":junctions,"segments":segments,"connections":connections,"turnouts":turnouts,"turntable":turntable,"zero_length_segments":zero,"counts":{"positionable_points":len(points),"segments":len(segments),"arcs":sum(s["source_kind"]=="arc" for s in segments.values()),"beziers":sum(s["source_kind"]=="bezier" for s in segments.values()),"straight":sum(s["source_kind"]=="straight" for s in segments.values()),"turnouts":len(turnouts)}}

def write_import(root: Path, source: Path=DEFAULT_SOURCE) -> dict:
    transform_path = root / "config/jmri_transform.yaml"
    transform = yaml.safe_load(transform_path.read_text()) if transform_path.exists() else {}
    data=import_jmri(source, **(transform or {}))
    (root/"config/jmri_layout_import.yaml").write_text(yaml.safe_dump(data,sort_keys=False))
    return data
