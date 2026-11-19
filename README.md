# HO Railroad Control

Raspberry Pi 4B-first, safety-oriented controller for the HO railroad. Hardware is the primary deployment target; simulation remains the safe developer default and physical outputs are never enabled implicitly.

## Run on macOS (safe simulation)

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
python -m railroad.main --mode simulation --dashboard
```

Open http://127.0.0.1:8080 for the local development server. The deployed hardware service listens on `0.0.0.0:8083`; the dashboard is reachable at `http://<lab1-address>:8083`. Simulation controls are unavailable when hardware mode is selected.

On a Raspberry Pi, complete wiring, current, fuse and controller checks and fill the
controller and relay configuration before using `--mode hardware`. There is no
physical emergency-stop input or E-Stop configuration. Startup remains
OFF/DISARMED; operator-authorized motion, global STOP, local STOP and watchdogs
remain in force. See [dispatcher STOP protocol](docs/DISPATCHER_STOP_PROTOCOL.md).

## Status

See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md). Physical hardware, ESP32 pin selections, IR receiver selection, and exact track topology remain unverified.
