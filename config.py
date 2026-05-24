import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = Path(os.environ.get("FST_OUTPUTS_DIR", str(BASE_DIR / "outputs")))
RAW_DIR = OUTPUTS_DIR / "raw"
PARSED_DIR = OUTPUTS_DIR / "parsed"
LOGS_DIR = Path(os.environ.get("FST_LOGS_DIR", str(BASE_DIR / "logs")))
DEFAULT_DB_PATH = Path(os.environ.get("FST_DB_PATH", str(OUTPUTS_DIR / "seat_tracker.sqlite3")))
WEB_HOST = os.environ.get("FST_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("FST_WEB_PORT", "5000"))

DEFAULT_EXCHANGE = "czce"
POLL_INTERVAL_MINUTES = 30
POLL_START_HOUR = 15
POLL_END_HOUR = 23
