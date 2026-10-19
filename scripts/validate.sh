#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/../backend"
python -m compileall -q app tests
python -m pip install -r requirements.txt
pytest -q
