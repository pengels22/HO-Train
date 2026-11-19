import json
import csv
import os
import tempfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from threading import Event
import socket
import time
from railroad.dispatcher import Dispatcher, SafetyError
from railroad.simulator.engine import SimulationEngine, SpeedProfile, Consist, Car
from railroad.geography import load_geography
from railroad.track_geometry import load_centerlines
from railroad.transport.locomotive import create_bench_sender
from railroad.transport.usb import ControllerRegistry, RegisteredController, pyserial_connector
from railroad.transport.telemetry import ControllerHealthRegistry
from railroad.transport.ir_bench import BenchIRReader
from railroad.hardware.registry import HardwareRegistry
from railroad.hardware.yard_power import YardPowerAdapter

DISPATCHER = Dispatcher()

ROOT = Path(__file__).resolve().parents[2]

def _load_paths():
    import yaml
    path = ROOT / "config/simulation_paths.yaml"
    return yaml.safe_load(path.read_text()) or {"verified": False, "paths": {}}

SIMULATION = SimulationEngine(DISPATCHER, _load_paths())
USB_CONTROLLERS = ControllerRegistry()
HEALTH = ControllerHealthRegistry(USB_CONTROLLERS)
TELEMETRY_STOP = None
TELEMETRY_SOCKET = None
IR_BENCH = None
IO_CONFIG_PATH = ROOT / "config" / "io_config.csv"
IO_CONFIG_STATE: list[dict] = []
IO_HARDWARE_REGISTRY: HardwareRegistry | None = None


IO_CONFIG_COLUMNS = ("controller", "channel", "device_type", "tag", "configuration_status", "bias")
IO_CONFIG_CONTROLLERS = {"motion1", "motion2", "inputs1", "inputs2", "ir"}
OUTPUT_TYPES = {"", "Motor", "Relay", "Servo", "Unassigned"}
INPUT_BIASES = {"", "Pull-up (internal)", "No bias"}


def _read_io_config():
    if not IO_CONFIG_PATH.exists():
        return []
    with IO_CONFIG_PATH.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _save_io_config(rows):
    """Persist the UI's controller map atomically on the Pi filesystem."""
    if not isinstance(rows, list) or len(rows) > 64:
        raise ValueError("rows must be a list of at most 64 channels")
    normalized = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each I/O row must be an object")
        controller = str(row.get("controller", ""))
        channel = str(row.get("channel", ""))
        if controller not in IO_CONFIG_CONTROLLERS:
            raise ValueError(f"unknown I/O controller: {controller}")
        if channel not in {f"CH{i}" for i in range(1, 17)}:
            raise ValueError(f"invalid channel: {channel}")
        key = (controller, channel)
        if key in seen:
            raise ValueError(f"duplicate I/O channel: {controller}/{channel}")
        seen.add(key)
        values = {key: str(row.get(key, "")).strip() for key in IO_CONFIG_COLUMNS}
        values["controller"], values["channel"] = controller, channel
        device = values["device_type"]
        if controller.startswith("motion") and device not in OUTPUT_TYPES:
            raise ValueError("motion channels support only Motor, Relay, Servo, or Unassigned")
        if controller.startswith("inputs") and device not in {"", "Digital Input", "Unassigned"}:
            raise ValueError("input channels support only Digital Input or Unassigned")
        if controller.startswith("inputs") and values["bias"] not in INPUT_BIASES:
            raise ValueError("input bias must be Pull-up (internal) or No bias")
        if controller == "ir" and channel not in {f"CH{i}" for i in range(1, 13)}:
            raise ValueError("IR receiver channels are CH1 through CH12")
        if any(len(value) > 120 for value in values.values()):
            raise ValueError("I/O fields must be 120 characters or less")
        normalized.append(values)
    IO_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="io_config.", suffix=".csv", dir=IO_CONFIG_PATH.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=IO_CONFIG_COLUMNS)
            writer.writeheader()
            writer.writerows(normalized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, IO_CONFIG_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return normalized


def _stop_telemetry_listener():
    global TELEMETRY_STOP, TELEMETRY_SOCKET
    if TELEMETRY_STOP: TELEMETRY_STOP.set()
    if TELEMETRY_SOCKET:
        try: TELEMETRY_SOCKET.close()
        except OSError: pass
    TELEMETRY_STOP = TELEMETRY_SOCKET = None


def _start_telemetry_listener():
    global TELEMETRY_STOP, TELEMETRY_SOCKET
    _stop_telemetry_listener()
    TELEMETRY_STOP = Event()
    TELEMETRY_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    TELEMETRY_SOCKET.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    TELEMETRY_SOCKET.bind(("0.0.0.0", 4211))
    TELEMETRY_SOCKET.settimeout(0.2)
    def loop():
        while TELEMETRY_STOP and not TELEMETRY_STOP.is_set():
            try:
                packet, _ = TELEMETRY_SOCKET.recvfrom(2048)
                HEALTH.update(packet)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as exc:
                if HEALTH.on_failure:
                    HEALTH.on_failure("locomotive-telemetry", str(exc))
    Thread(target=loop, name="locomotive-telemetry", daemon=True).start()


def _stop_ir_bench():
    global IR_BENCH
    if IR_BENCH:
        IR_BENCH.stop()
    IR_BENCH = None


def _start_ir_bench(hardware):
    global IR_BENCH
    import yaml
    _stop_ir_bench()
    config = hardware.get("bench_ir_receiver", {}) or {}
    if not config.get("enabled") or not config.get("port"):
        return
    ir_config = yaml.safe_load((ROOT / "config/ir_receivers.yaml").read_text()) or {}
    receiver_map = {}
    for receiver in ir_config.get("receivers", []) or []:
        receiver_id = receiver.get("id")
        if not receiver_id:
            continue
        if receiver.get("channel") is not None:
            receiver_map[("channel", str(receiver["channel"]).upper())] = receiver_id
        if receiver.get("pin"):
            receiver_map[("pin", str(receiver["pin"]).upper())] = receiver_id
    IR_BENCH = BenchIRReader(config["port"], int(config.get("baudrate", 115200)),
                             lambda event: DISPATCHER.process_ir_event(event),
                             receiver_map=receiver_map)
    IR_BENCH.start()


def load_locomotive_controller_config(hardware: dict, known_ids: set[int]) -> list[dict]:
    """Validate the declarative four-locomotive controller inventory."""
    entries = hardware.get("locomotive_controllers") or []
    allowed = {"m5_atom_echo", "xiao_esp32_c6"}
    ids = []
    for entry in entries:
        if not isinstance(entry, dict) or type(entry.get("id")) is not int:
            raise RuntimeError("locomotive_controllers entries require integer id and type")
        if entry.get("type") not in allowed:
            raise RuntimeError(f"unsupported locomotive controller type: {entry.get('type')}")
        ids.append(entry["id"])
    if len(ids) != len(set(ids)) or any(i < 1 or i > 4 for i in ids) or not set(ids) <= known_ids:
        raise RuntimeError("invalid or inconsistent locomotive_controllers IDs")
    return [dict(entry) for entry in entries]


def configure_runtime(mode: str = "simulation") -> None:
    """Configure the command gate; network transmission is never implicit."""
    global USB_CONTROLLERS, HEALTH, IO_CONFIG_STATE, IO_HARDWARE_REGISTRY
    if mode not in {"simulation", "hardware", "bench"}:
        raise ValueError("mode must be simulation, hardware, or bench")
    if mode == "simulation":
        _stop_telemetry_listener()
        _stop_ir_bench()
        if DISPATCHER.motion_transport:
            shutdown = getattr(DISPATCHER.motion_transport, "shutdown", None)
            if shutdown:
                shutdown()
            DISPATCHER.motion_transport = None
        USB_CONTROLLERS.close()
        HEALTH.stop_monitor()
        USB_CONTROLLERS = ControllerRegistry()
        HEALTH = ControllerHealthRegistry(USB_CONTROLLERS)
        DISPATCHER.attach_controller_health(HEALTH)
        DISPATCHER.yard_adapter = None
        IO_CONFIG_STATE = []
        IO_HARDWARE_REGISTRY = None
        DISPATCHER.accessory_errors.clear()
        DISPATCHER.simulation = True
        DISPATCHER.disarm()
        return
    # Hardware and bench modes are explicit opt-ins; no physical stop switch required.
    import yaml
    hardware = yaml.safe_load((ROOT / "config/hardware.yaml").read_text()) or {}
    # Re-load the Pi-persisted editor data through the same validator used by
    # POST. This is the authoritative runtime view; browser local storage is
    # never consulted by hardware adapters.
    IO_CONFIG_STATE = _save_io_config(_read_io_config()) if IO_CONFIG_PATH.exists() else []
    IO_HARDWARE_REGISTRY = HardwareRegistry.from_config(hardware).require_valid()
    controller_transport_config = hardware.get("controller_transport", {}) or {}
    configured = yaml.safe_load((ROOT / "config/locomotives.yaml").read_text()) or {}
    known_ids = {int(item["id"]) for item in configured.get("locomotives", [])}
    locomotive_config = load_locomotive_controller_config(hardware, known_ids)
    USB_CONTROLLERS = ControllerRegistry()
    for entry in controller_transport_config.get("serial_controllers", []) or []:
        controller_id, port_name = entry.get("id"), entry.get("port")
        if not controller_id or not port_name:
            continue
        baudrate = int(entry.get("baudrate", controller_transport_config.get("serial_baudrate", 115200)))
        connector = lambda port, baudrate=baudrate: pyserial_connector(port, baudrate=baudrate)
        USB_CONTROLLERS.controllers.append(RegisteredController(
            controller_id, port_name, connector,
            controller_type=entry.get("type", "usb_controller")))
    locomotive_ids = [int(i["id"]) for i in hardware.get("locomotive_controllers", [])]
    HEALTH = ControllerHealthRegistry(
        USB_CONTROLLERS, locomotive_ids=locomotive_ids,
        locomotive_types={int(item["id"]): item["type"] for item in locomotive_config},
        independent_locomotives=True)
    DISPATCHER.attach_controller_health(HEALTH)
    # Build the validated yard adapter without a writer until mappings are
    # commissioned. This makes activation fail explicitly instead of guessing
    # a Pi GPIO or claiming power is verified.
    DISPATCHER.yard_adapter = YardPowerAdapter.from_config(hardware)
    DISPATCHER.simulation = False
    DISPATCHER.bench_mode = mode == "bench"
    # Healthy locomotive operation is independent of accessory availability.
    DISPATCHER.attach_motion_transport(create_bench_sender(enable_network=True, controllers=USB_CONTROLLERS, start_armed=True), require_rearm=False)
    HEALTH.on_failure = None
    USB_CONTROLLERS.start_heartbeat()
    HEALTH.start_monitor()
    _start_ir_bench(hardware)
    _start_telemetry_listener()

class DashboardHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/api/control":
            self._control_command()
            return
        if self.path == "/api/io-config":
            self._save_io_config()
            return
        if self.path == "/api/simulation":
            self._simulation_command()
            return
        if self.path == "/api/simulation/calibration":
            self._save_calibration()
            return
        if self.path == "/api/geography/marker":
            self._save_geography_marker()
            return
        if self.path == "/api/track-geometry":
            self._save_track_geometry()
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
            HEALTH.check_freshness()
            status = DISPATCHER.snapshot()
            status["simulation"] = SIMULATION.snapshot()
            status["stop_transport"] = {"registered_usb": USB_CONTROLLERS.status()}
            bench = IR_BENCH.status() if IR_BENCH else {"enabled": False, "connected": False}
            status["bench_ir_receiver"] = bench
            # The Nano is a real, read-only controller in hardware mode.  Keep
            # it in the same inventory as the locomotive and accessory boards
            # so the headline count reflects every connected controller.
            status["controllers"].append({
                "id": "nano-ir-bench",
                "type": "arduino_nano_esp32_ir",
                "required": False,
                "connected": bool(bench.get("connected")),
                "port": bench.get("port"),
                "state": "RECEIVING" if bench.get("connected") else None,
                "faults": (["receiver_unavailable"] if bench.get("last_error") else []),
                "status": {
                    "controller": "nano_ir_bench",
                    "events": bench.get("events", 0),
                    "last_event": bench.get("last_event"),
                },
            })
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
            geo = load_geography(ROOT)
            zones = [{"id": zone_id, "railway": value.get("track_path"), "state": "UNKNOWN",
                      "occupying_train": None, "reserved_train": None} for zone_id, value in geo["zones"].items()]
            body = json.dumps({"verified": False, "zones": zones}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/zone-boundaries":
            geo = load_geography(ROOT)
            body = json.dumps({"verified": False, "coordinate_system": geo["coordinate_system"], "boundaries": geo["zones"]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/config":
            import yaml
            hardware = yaml.safe_load((ROOT / "config/hardware.yaml").read_text()) or {}
            ir = yaml.safe_load((ROOT / "config/ir_receivers.yaml").read_text()) or {}
            locomotives = yaml.safe_load((ROOT / "config/locomotives.yaml").read_text()) or {}
            wifi = locomotives.get("wifi", {})
            io = [{"device": "Raspberry Pi GPIO", "io": "unassigned", "location": "Raspberry Pi", "function": "general-purpose I/O", "polarity": "n/a", "status": "reserved"}]
            registry = IO_HARDWARE_REGISTRY or HardwareRegistry.from_config(hardware).require_valid()
            io = [{"device": entry.device_type, "io": f"{entry.board}:{entry.channel}",
                   "address": entry.address, "location": entry.location,
                   "function": entry.function, "direction": entry.direction,
                   "polarity": entry.polarity,
                   "status": "spare" if entry.spare else ("active" if entry.active else "reserved")}
                  for entry in registry.entries]
            for board, address in (hardware.get("i2c", {}).get("boards", {}) or {}).items():
                device = "MCP23017" if board.startswith("sensors") else ("PCA9685" if board in {"motor_1", "motor_2", "servo"} else "I2C / " + board)
                io.append({"device": device, "io": hex(address) if isinstance(address, int) else str(address), "location": "Raspberry Pi I2C", "function": board, "polarity": "n/a", "status": "configured"})
            for receiver in ir.get("receivers", []):
                io.append({"device": "Arduino Nano", "io": receiver.get("pin", "unassigned"), "location": ", ".join(receiver.get("zones", [])) or "Yard", "function": receiver.get("description", "IR receiver"), "polarity": "active_high", "status": "configured"})
            body = json.dumps({"io": io, "registry_errors": registry.validate(), "io_config": _read_io_config(), "locomotives": locomotives.get("locomotives", []), "controller": {"hardware_mode": hardware.get("mode", "simulation"), "i2c_bus": hardware.get("i2c", {}).get("bus", 1), "wifi_ssid": wifi.get("ssid", ""), "controller_ip": wifi.get("controller_ip", ""), "udp_broadcast": wifi.get("broadcast", ""), "udp_port": wifi.get("udp_port", 4210), "yard_relays": hardware.get("yard_outputs", [])}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/io-config":
            self._json_response({"ok": True, "path": str(IO_CONFIG_PATH), "rows": _read_io_config()})
        elif self.path == "/api/geography":
            body = json.dumps(load_geography(ROOT)).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/track-geometry":
            geo = load_geography(ROOT)
            body = json.dumps({"verified": geo["geometry_verified"], "coordinate_system": geo["coordinate_system"],
                               "width": geo["image"]["width"], "height": geo["image"]["height"],
                               "segments": geo["segments"], "junctions": geo["junctions"], "terminals": geo["terminals"],
                               "connections": geo["connections"], "turnouts": geo["turnout_graph"],
                               "yard_tracks": geo["yard_tracks"], "validation": {"ok": geo["graph_valid"], "errors": geo["graph_errors"]}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path in ("/", "/track-map"):
            self._serve_dashboard_file("index.html", "text/html; charset=utf-8")
        elif self.path.startswith("/dashboard/"):
            relative = self.path.removeprefix("/dashboard/").split("?", 1)[0]
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
        self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store, no-cache, must-revalidate"); self.send_header("Pragma", "no-cache"); self.end_headers(); self.wfile.write(body)

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
            if payload.get("geometry"):
                geometry_path = ROOT / "config/marker_geometry_v05.yaml"
                geometry = yaml.safe_load(geometry_path.read_text()) or {}
                geometry.setdefault("markers", {}).setdefault(marker_id, {})
                geometry["markers"][marker_id].update({k: payload["geometry"][k] for k in ("track_path", "segment_id", "distance_px", "alignment_error_px") if k in payload["geometry"]})
                geometry_path.write_text(yaml.safe_dump(geometry, sort_keys=False))
            body = json.dumps({"saved": True, "kind": kind, "id": marker_id, "position": section[marker_id]["position"], "verified": bool(section[marker_id].get("verified", False))}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            body = json.dumps({"saved": False, "error": str(exc)}).encode()
            self.send_response(400); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _save_track_geometry(self):
        import yaml
        from railroad.track_geometry import validate_graph
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            segments = payload["segments"]
            if not isinstance(segments, dict) or any(len(p.get("points", [])) < 2 for p in segments.values()):
                raise ValueError("each rail segment needs at least two points")
            data = {"verified": False, "coordinate_system": "clean_image_pixels", "width": 752, "height": 602,
                    "terminals": payload.get("terminals", []), "junctions": payload.get("junctions", {}),
                    "segments": segments, "connections": payload.get("connections", []),
                    "yard_tracks": payload.get("yard_tracks", {})}
            validation = validate_graph(data)
            if not validation["ok"]:
                raise ValueError("; ".join(validation["errors"]))
            target = ROOT / "config/jmri_layout_import.yaml" if (ROOT / "config/jmri_layout_import.yaml").exists() else ROOT / "config/track_centerlines.yaml"
            existing = yaml.safe_load(target.read_text()) if target.exists() else {}
            data = {**(existing or {}), **data}
            target.write_text(yaml.safe_dump(data, sort_keys=False))
            self._json_response({"saved": True, "verified": False, "segments": segments, "validation": validation})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json_response({"saved": False, "error": str(exc)}, 400)
    def _json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def _json_response(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _save_io_config(self):
        global IO_CONFIG_STATE
        try:
            rows = _save_io_config(self._json_body().get("rows"))
            IO_CONFIG_STATE = rows
            self._json_response({"ok": True, "path": str(IO_CONFIG_PATH), "rows": rows})
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json_response({"ok": False, "error": str(exc)}, 400)

    def _simulation_command(self):
        try:
            if not DISPATCHER.simulation:
                raise SafetyError("simulation API is disabled in hardware mode")
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
            elif action == "rearm": DISPATCHER.rearm()
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
        except (KeyError, TypeError, ValueError, RuntimeError, SafetyError) as exc:
            self._json_response({"ok": False, "error": str(exc)}, 400)

    def _control_command(self):
        """Explicit hardware dispatcher and connected-controller controls."""
        try:
            payload = self._json_body()
            action = payload.get("action")
            if action == "global_stop":
                DISPATCHER.stop_all("operator global stop")
            elif action == "clear_stop":
                DISPATCHER.clear_stop()
            elif action == "rearm":
                DISPATCHER.rearm()
            elif action == "set_operator_mode":
                DISPATCHER.set_operator_mode(payload["mode"])
            elif action == "start_dispatcher":
                DISPATCHER.start_dispatcher()
            elif action == "stop_dispatcher":
                DISPATCHER.stop_dispatcher()
            elif action == "run_cycle_once":
                DISPATCHER.run_cycle_once()
            elif action == "set_train_mode":
                DISPATCHER.set_train_mode(int(payload["train_id"]), payload["mode"])
            elif action == "yard_power":
                DISPATCHER.set_yard_power(payload["track"], bool(payload["enabled"]))
            elif action == "clear_yard_assignments":
                DISPATCHER.clear_yard_assignments()
            elif action == "accessory_request":
                DISPATCHER.record_accessory_request(payload["accessory"], payload["command"])
            elif action == "assign_destination":
                train_id = int(payload["train_id"])
                destination = str(payload["destination"])
                # Assignment changes dispatcher state only; it never issues
                # a motion command to a locomotive or accessory.
                DISPATCHER.assign_destination(train_id, destination)
            elif action == "stop_train":
                DISPATCHER.stop_train(int(payload["train_id"]))
            elif action == "command_motion":
                DISPATCHER.command_motion(int(payload["train_id"]), int(payload["speed"]))
            elif action == "controller_command":
                controller_id = str(payload["controller_id"])
                command = str(payload["command"])
                fields = payload.get("fields", {})
                if not isinstance(fields, dict):
                    raise TypeError("controller fields must be an object")
                USB_CONTROLLERS.command(controller_id, command, fields=fields)
            else:
                raise ValueError("unknown control action")
            self._json_response({"ok": True, "action": action, "status": DISPATCHER.snapshot()})
        except (KeyError, TypeError, ValueError, RuntimeError, SafetyError) as exc:
            self._json_response({"ok": False, "error": str(exc)}, 400)

    def _save_calibration(self):
        import yaml
        try:
            if not DISPATCHER.simulation:
                raise SafetyError("simulation calibration is disabled in hardware mode")
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

def serve(host="127.0.0.1", port=8080, mode="simulation"):
    configure_runtime(mode)
    def tick_loop():
        while True:
            SIMULATION.tick()
            time.sleep(0.05)
    Thread(target=tick_loop, daemon=True, name="simulation-clock").start()
    ThreadingHTTPServer((host, port), DashboardHandler).serve_forever()
