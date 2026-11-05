#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
echo 'Simulation validated. Review safety documentation before enabling hardware.'
