#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 run_rf_shazam.py --ui --host 127.0.0.1 --port 5000
