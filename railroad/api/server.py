import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time
from railroad.dispatcher import Dispatcher, SafetyError
from railroad.simulator.engine import SimulationEngine, SpeedProfile, Consist, Car
from railroad.geography import load_geography

DISPATCHER = Dispatcher()

ROOT = Path(__file__).resolve().parents[2]

def _load_paths():
    import yaml
    path = ROOT / "config/simulation_paths.yaml"
    return yaml.safe_load(path.read_text()) or {"verified": False, "paths": {}}

SIMULATION = SimulationEngine(DISPATCHER, _load_paths())

class DashboardHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/api/simulation":
            self._simulation_command()
            return
        if self.path == "/api/simulation/calibration":
            self._save_calibration()
            return
        if self.path == "/api/geography/marker":
            self._save_geography_marker()
            return
        if self.path != "/api/zones/boundaries":
            self.send_error(404); return
        import yaml
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            zone_id = payload["zone_id"]
            if "start" not in payload or "end" not in payload:
                raise ValueError("polygon boundaries are obsolete; provide START and END pairs")
            start, end = payload["start"], payload["end"]
            if any(len(p) != 2 or not all(0 <= float(v) <= 1 for v in p) for p in (start, end)):
                raise ValueError("START and END must be normalized x/y pairs")
            markers = {"start": [float(x) for x in start], "end": [float(x) for x in end], "calibrated": False}
            path = ROOT / "config/zone_boundaries.yaml"
            data = yaml.safe_load(path.read_text())
            if zone_id not in data["boundaries"]:
                raise ValueError("unknown zone")
            previous = data["boundaries"].get(zone_id, {})
            data["boundaries"][zone_id] = {**previous, **markers, "verified": False}
            path.write_text(yaml.safe_dump(data, sort_keys=False))
            body = json.dumps({"saved": True, "zone_id": zone_id, "verified": False, "start": data["boundaries"][zone_id]["start"], "end": data["boundaries"][zone_id]["end"]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            body = json.dumps({"saved": False, "error": str(exc)}).encode()
            self.send_response(400); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            DISPATCHER.check_deadlines()
            status = DISPATCHER.snapshot()
            status["simulation"] = SIMULATION.snapshot()
            body = json.dumps(status).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/simulation":
            body = json.dumps(SIMULATION.snapshot()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/simulation/events":
            body = json.dumps({"events": SIMULATION.events[-100:]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/simulation/calibration":
            body = json.dumps(SIMULATION.paths).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/zones":
            import yaml
            data = yaml.safe_load((ROOT / "config/zones.yaml").read_text())
            body = json.dumps({"verified": False, "zones": [{**z, "state": "UNKNOWN", "occupying_train": None, "reserved_train": None} for z in data["zones"]]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/zone-boundaries":
            import yaml
            data = yaml.safe_load((ROOT / "config/zone_boundaries.yaml").read_text())
            body = json.dumps(data).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/config":
            import yaml
            hardware = yaml.safe_load((ROOT / "config/hardware.yaml").read_text()) or {}
            ir = yaml.safe_load((ROOT / "config/ir_receivers.yaml").read_text()) or {}
            locomotives = yaml.safe_load((ROOT / "config/locomotives.yaml").read_text()) or {}
            wifi = locomotives.get("wifi", {})
            io = [{"device": "Raspberry Pi GPIO", "io": "unassigned", "location": "Raspberry Pi", "function": "general-purpose I/O", "polarity": "n/a", "status": "reserved"}]
            for board, address in (hardware.get("i2c", {}).get("boards", {}) or {}).items():
                device = "MCP23017" if board.startswith("sensors") else ("PCA9685" if board in {"motor_1", "motor_2", "servo"} else "I2C / " + board)
                io.append({"device": device, "io": hex(address) if isinstance(address, int) else str(address), "location": "Raspberry Pi I2C", "function": board, "polarity": "n/a", "status": "configured"})
            for receiver in ir.get("receivers", []):
                io.append({"device": "Arduino Nano", "io": receiver.get("pin", "unassigned"), "location": ", ".join(receiver.get("zones", [])) or "Yard", "function": receiver.get("description", "IR receiver"), "polarity": "active_high", "status": "configured"})
            body = json.dumps({"io": io, "locomotives": locomotives.get("locomotives", []), "controller": {"hardware_mode": hardware.get("mode", "simulation"), "i2c_bus": hardware.get("i2c", {}).get("bus", 1), "wifi_ssid": wifi.get("ssid", ""), "controller_ip": wifi.get("controller_ip", ""), "udp_broadcast": wifi.get("broadcast", ""), "udp_port": wifi.get("udp_port", 4210), "yard_relays": "3 physical sections (1A + 1B share Track 1)"}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/geography":
            body = json.dumps(load_geography(ROOT)).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path in ("/", "/track-map"):
            self._serve_dashboard_file("index.html", "text/html; charset=utf-8")
        elif self.path.startswith("/dashboard/"):
            relative = self.path.removeprefix("/dashboard/")
            types = {".css": "text/css", ".js": "application/javascript", ".png": "image/png", ".html": "text/html; charset=utf-8"}
            self._serve_dashboard_file(relative, types.get(Path(relative).suffix, "application/octet-stream"))
        elif self.path == "/zones":
            body = b'''<!doctype html><meta charset="utf-8"><title>HO Railroad Zones</title><style>body{background:#111;color:#eee;font:16px sans-serif}main{max-width:1200px;margin:auto}img{max-width:100%;border:1px solid #555}.note{color:#ffd85a}</style><main><h1>Operating Zones</h1><p class="note">Proposed overlay only. Zone geometry and topology are unverified; live routing is disabled.</p><img src="/assets/layout/zone-overlay-preview.svg" alt="Proposed 15-zone overlay"></main>'''
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/zones/edit":
            body = b'''<!doctype html><meta charset="utf-8"><title>Edit proposed zones</title><style>body{background:#111;color:#eee;font:16px sans-serif}main{max-width:1200px;margin:auto}input{width:90%;background:#222;color:#eee;border:1px solid #555;padding:6px}button{padding:7px;margin:4px}.note{color:#ffd85a}</style><main><h1>Proposed zone editor</h1><p class="note">Simulation/configuration only. Saves force verified=false and cannot authorize hardware routing.</p><p>Zone ID <input id="zone" value="MAIN-1"></p><p>Polygon JSON <input id="polygon" value="[[0.3,0.4],[0.6,0.4],[0.6,0.55],[0.3,0.55]]"></p><button onclick="save()">Save proposed boundary</button><pre id="result"></pre><script>async function save(){let r=await fetch('/api/zones/boundaries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({zone_id:document.querySelector('#zone').value,polygon:JSON.parse(document.querySelector('#polygon').value)})});document.querySelector('#result').textContent=await r.text()}</script></main>'''
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path.startswith("/assets/layout/"):
            relative = self.path.removeprefix("/assets/layout/")
            asset = (ROOT / "assets/layout" / relative).resolve()
            if ROOT / "assets/layout" not in asset.parents or not asset.is_file():
                self.send_error(404); return
            content_type = "image/png" if asset.suffix == ".png" else "image/svg+xml"
            body = asset.read_bytes()
            self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            body = b"<html><body><h1>HO Railroad Control</h1><p>Simulation dashboard</p><a href='/api/status'>status</a> | <a href='/zones'>zones</a></body></html>"
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _serve_dashboard_file(self, relative: str, content_type: str) -> None:
        root = ROOT / "dashboard" / "public"
        asset = (root / relative).resolve()
        if root not in asset.parents or not asset.is_file():
            self.send_error(404); return
        body = asset.read_bytes()
        self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _save_geography_marker(self):
        import yaml
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            kind, marker_id, position = payload["kind"], payload["id"], payload["position"]
            if kind not in {"receiver", "turnout"} or len(position) != 2 or any(not 0 <= float(v) <= 1 for v in position):
                raise ValueError("marker must be a normalized receiver or turnout position")
            path = ROOT / "config/geography_design_v05.yaml"
            data = yaml.safe_load(path.read_text()) or {}
            section = data["receivers"] if kind == "receiver" else data["turnouts"]
            if marker_id not in section:
                raise ValueError("unknown geography marker")
            section[marker_id]["position"] = [float(position[0]), float(position[1])]
            path.write_text(yaml.safe_dump(data, sort_keys=False))
            body = json.dumps({"saved": True, "kind": kind, "id": marker_id, "position": section[marker_id]["position"], "verified": bool(section[marker_id].get("verified", False))}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            body = json.dumps({"saved": False, "error": str(exc)}).encode()
            self.send_response(400); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def _json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def _json_response(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _simulation_command(self):
        try:
            payload = self._json_body()
            action = payload.get("action")
            if action == "start": SIMULATION.start()
            elif action == "pause": SIMULATION.pause()
            elif action == "resume": SIMULATION.resume()
            elif action == "reset": SIMULATION.reset()
            elif action == "speed": SIMULATION.set_speed(float(payload["multiplier"]))
            elif action == "fault": SIMULATION.inject_fault(payload["fault"], payload.get("train_id"))
            elif action == "global_stop": DISPATCHER.stop_all(payload.get("reason", "operator global stop"))
            elif action == "clear_stop": DISPATCHER.clear_stop()
            elif action == "reconcile":
                event = type("SimEvent", (), {"train_id": int(payload["train_id"]), "receiver_id": payload["receiver"], "timestamp": SIMULATION.sim_time})()
                DISPATCHER.process_ir_event(event, zone=payload.get("zone"))
                DISPATCHER.clear_stop()
            elif action == "load": SIMULATION.load(int(payload["train_id"]), payload["location"])
            elif action == "tipper": SIMULATION.unload_tipper(int(payload["train_id"]), success=payload.get("success", True), safe_to_depart=payload.get("safe_to_depart", True))
            elif action == "yard_power": SIMULATION.set_yard_power(payload["track"], payload["enabled"])
            elif action == "park": SIMULATION.park(int(payload["train_id"]), payload["stall"])
            elif action == "dispatch":
                profile = SpeedProfile(**payload.get("profile", {}))
                consist = Consist(tuple(Car(**c) for c in payload.get("cars", [{"length_mm": 120.0, "spacing_mm": 25.0, "magnetic_strip": True}])))
                SIMULATION.dispatch(int(payload["train_id"]), payload["path_id"], target_speed_mm_s=payload.get("target_speed_mm_s"), profile=profile, consist=consist)
            else: raise ValueError("unknown simulation action")
            self._json_response({"ok": True, "simulation": SIMULATION.snapshot()})
        except (KeyError, TypeError, ValueError, SafetyError) as exc:
            self._json_response({"ok": False, "error": str(exc)}, 400)

    def _save_calibration(self):
        import yaml
        try:
            payload = self._json_body()
            paths = payload.get("paths", {})
            if not isinstance(paths, dict): raise ValueError("paths must be an object")
            for path_id, path in paths.items():
                points = path.get("points", [])
                if len(points) < 2 or any(len(p) != 2 or not all(0 <= float(v) <= 1 for v in p) for p in points):
                    raise ValueError(f"{path_id}: at least two normalized points are required")
                if float(path.get("length_mm", 0)) <= 0: raise ValueError(f"{path_id}: length_mm must be positive")
            data = {"verified": bool(payload.get("verified", False)), "source_image": "dashboard/public/images/railroad-layout-clean.png", "paths": paths}
            (ROOT / "config/simulation_paths.yaml").write_text(yaml.safe_dump(data, sort_keys=False))
            SIMULATION.paths = data
            SIMULATION._log("calibration_saved", verified=data["verified"], paths=len(paths))
            self._json_response({"ok": True, "geometry_available": SIMULATION.geometry_available})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json_response({"ok": False, "error": str(exc)}, 400)

def serve(host="127.0.0.1", port=8080):
    def tick_loop():
        while True:
            SIMULATION.tick()
            time.sleep(0.05)
    Thread(target=tick_loop, daemon=True, name="simulation-clock").start()
    ThreadingHTTPServer((host, port), DashboardHandler).serve_forever()
