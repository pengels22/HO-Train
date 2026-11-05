import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class DashboardHandler(BaseHTTPRequestHandler):
    state = {"mode": "simulation", "emergency_stop": False, "trains": 4}
    def do_GET(self):
        if self.path == "/api/status":
            body = json.dumps(self.state).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            body = b"<html><body><h1>HO Railroad Control</h1><p>Simulation dashboard</p><a href='/api/status'>status</a></body></html>"
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

def serve(host="127.0.0.1", port=8080):
    ThreadingHTTPServer((host, port), DashboardHandler).serve_forever()
