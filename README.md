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

On a Raspberry Pi, complete the wiring/current checks and fill the explicit E-Stop,
controller, and relay configuration before using `--mode hardware`. Startup remains
OFF/DISARMED; an operator must explicitly rearm after bench checks.

## Status

See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md). Physical hardware, ESP32 pin selections, IR receiver selection, and exact track topology remain unverified.
