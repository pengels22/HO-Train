"""Read-only serial integration for the single Nano ESP32 bench IR receiver."""
from __future__ import annotations

import json
import logging
import time
from threading import Event, Lock, Thread

from railroad.tracking.ir_serial import parse_event
from railroad.tracking.receivers import ReceiverEvent


class BenchIRReader:
    """Consume validated bench events without sending commands to the board."""

    def __init__(self, port: str, baudrate: int, on_event, *, retry_s: float = 2.0):
        self.port = port
        self.baudrate = int(baudrate)
        self.on_event = on_event
        self.retry_s = float(retry_s)
        self.logger = logging.getLogger("ho-ir-bench")
        self._stop = Event()
        self._thread: Thread | None = None
        self._serial = None
        self._lock = Lock()
        self.connected = False
        self.last_event: dict | None = None
        self.last_error: str | None = None
        self.events = 0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="ho-ir-bench", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            serial_port = self._serial
            self._serial = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        self._thread = None
        self.connected = False

    def status(self) -> dict:
        return {"port": self.port, "baudrate": self.baudrate,
                "connected": self.connected, "events": self.events,
                "last_event": self.last_event, "last_error": self.last_error}

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                import serial
                serial_port = serial.Serial(self.port, self.baudrate, timeout=0.5)
                with self._lock:
                    self._serial = serial_port
                self.connected = True
                self.last_error = None
                self.logger.info("bench IR receiver connected on %s", self.port)
                while not self._stop.is_set():
                    line = serial_port.readline()
                    if line:
                        self._handle_line(line)
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                self.logger.warning("bench IR receiver unavailable on %s: %s", self.port, exc)
            finally:
                with self._lock:
                    current = self._serial
                    self._serial = None
                if current is not None:
                    try:
                        current.close()
                    except Exception:
                        pass
            self._stop.wait(self.retry_s)

    def _handle_line(self, line: bytes) -> None:
        try:
            payload = json.loads(line.decode("utf-8"))
            event = parse_event(json.dumps(payload, separators=(",", ":")))
            receiver = event["receiver"]
            now = time.monotonic()
            self.on_event(ReceiverEvent(receiver, event["train_id"], now))
            self.events += 1
            self.last_event = {"receiver": receiver, "train_id": event["train_id"], "timestamp": now}
            self.logger.info("bench IR event receiver=%s train=%s", receiver, event["train_id"])
        except Exception as exc:
            if line.lstrip().startswith(b"{"):
                self.logger.warning("ignored bench IR line: %s (%s)", line.decode(errors="replace").strip(), exc)
