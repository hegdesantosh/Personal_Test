#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
pip install -r requirements.txt --quiet --break-system-packages 2>/dev/null || true
echo "Starting Garmin Map Dashboard at http://localhost:5000"
python3 app.py
