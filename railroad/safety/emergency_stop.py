"""Physical E-Stop monitor; activation deliberately bypasses debounce."""
from __future__ import annotations
from threading import Event, Thread


class EmergencyStop:
    """Poll a GPIO input and drive the dispatcher's latched E-Stop."""
    def __init__(self, gpio, dispatcher, poll_period_s: float = 0.01):
        self.gpio = gpio
        self.dispatcher = dispatcher
        self.poll_period_s = poll_period_s
        self._stop = Event()
        self._thread: Thread | None = None
        self._seen_pressed = False

    def poll_once(self) -> None:
        pressed = bool(self.gpio.estop_pressed)
        if pressed and not self._seen_pressed:
            # No 250 ms debounce: a low input is safety-critical.
            self.dispatcher.stop_all("physical E-Stop pressed")
        elif not pressed and self._seen_pressed:
            # Release only stops repetition. Global stop and rearm latch remain.
            self.dispatcher.release_estop()
        self._seen_pressed = pressed

    def start(self) -> None:
        self.poll_once()
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="physical-estop", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_period_s):
            self.poll_once()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
