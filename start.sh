#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(dirname "$APP_DIR")"
DATA_DIR="${FST_OUTPUTS_DIR:-/opt/futures_seat_tracker/data}"
LOG_DIR="${FST_LOGS_DIR:-/opt/futures_seat_tracker/logs}"
DB_PATH="${FST_DB_PATH:-$DATA_DIR/seat_tracker.sqlite3}"
WEB_HOST="${FST_WEB_HOST:-0.0.0.0}"
WEB_PORT="${FST_WEB_PORT:-5000}"
PYTHON_BIN="${PYTHON_BIN:-python3.9}"

mkdir -p "$DATA_DIR" "$LOG_DIR"
cd "$APP_DIR"

export FST_OUTPUTS_DIR="$DATA_DIR"
export FST_LOGS_DIR="$LOG_DIR"
export FST_DB_PATH="$DB_PATH"
export FST_WEB_HOST="$WEB_HOST"
export FST_WEB_PORT="$WEB_PORT"

"$PYTHON_BIN" -m pip install -r requirements.txt
exec "$PYTHON_BIN" main.py serve
