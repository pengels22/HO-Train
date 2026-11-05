# HO Railroad Control

Simulation-first, safety-oriented Python foundation for the HO railroad controller. The default mode is simulation and hardware outputs are never enabled implicitly.

## Run on macOS

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
python -m railroad.main --mode simulation --dashboard
```

Open http://127.0.0.1:8080. The dashboard is intentionally local and read/control endpoints are guarded by simulation mode until authentication is added for live hardware.

## Status

See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md). Physical hardware, ESP32 pin selections, IR receiver selection, and exact track topology remain unverified.
