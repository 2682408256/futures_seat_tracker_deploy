from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from futures_seat_tracker.analysis.dominant_contracts import get_dominant_contract, get_dominant_contract_candidates
from futures_seat_tracker.analysis.rollover import get_dominant_switches
from futures_seat_tracker.collectors.czce import CzceCollector
from futures_seat_tracker.config import DEFAULT_DB_PATH, POLL_END_HOUR, POLL_INTERVAL_MINUTES, POLL_START_HOUR, WEB_HOST, WEB_PORT
from futures_seat_tracker.parsers.czce import parse_czce_file
from futures_seat_tracker.parsers.dce import parse_dce_zip
from futures_seat_tracker.parsers.shfe import parse_shfe_file
from futures_seat_tracker.storage.csv_writer import CsvWriter
from futures_seat_tracker.storage.db import Database
from futures_seat_tracker.storage.importer import CsvImporter

TIMEZONE = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument("--exchange", default="czce")

    db_parser = argparse.ArgumentParser(add_help=False)
    db_parser.add_argument("--db-file")

    backfill = subparsers.add_parser("backfill", parents=[common_parser, db_parser])
    backfill.add_argument("--date", required=True)

    parse_cmd = subparsers.add_parser("parse", parents=[common_parser])
    parse_cmd.add_argument("--file", required=True)
    parse_cmd.add_argument("--date")

    poll = subparsers.add_parser("poll", parents=[common_parser, db_parser])
    poll.add_argument("--date")
    poll.add_argument("--once", action="store_true")
    poll.add_argument("--skip-time-window", action="store_true")

    dominant_contract_cmd = subparsers.add_parser("dominant-contract", parents=[common_parser, db_parser])
    dominant_contract_cmd.add_argument("--date", required=True)
    dominant_contract_cmd.add_argument("--product", required=True)

    dominant_switch_cmd = subparsers.add_parser("dominant-switch", parents=[common_parser, db_parser])
    dominant_switch_cmd.add_argument("--product", required=True)
    dominant_switch_cmd.add_argument("--start-date")
    dominant_switch_cmd.add_argument("--end-date")

    backfill_range_cmd = subparsers.add_parser("czce-backfill-range", parents=[db_parser])
    backfill_range_cmd.add_argument("--start-date", required=True)
    backfill_range_cmd.add_argument("--end-date", required=True)

    subparsers.add_parser("init-db", parents=[db_parser])

    import_csv_cmd = subparsers.add_parser("import-csv", parents=[common_parser, db_parser])
    import_csv_cmd.add_argument("--date", required=True)

    subparsers.add_parser("serve", parents=[db_parser])

    return parser.parse_args()


def get_trade_date(date_arg: str | None = None) -> str:
    if date_arg:
        return date_arg
    return datetime.now(TIMEZONE).strftime("%Y%m%d")


def process_trade_date(exchange: str, trade_date: str, db_file: str | None = None) -> bool:
    if exchange != "czce":
        raise ValueError(f"Automatic download is only supported for czce, got: {exchange}")

    collector = CzceCollector()
    result = collector.download(trade_date)
    if not result.found:
        print(f"No data for {trade_date}: {result.source_url}")
        return False

    instruments, rankings, totals = parse_czce_file(result.file_path, exchange=result.exchange)
    writer = CsvWriter()
    outputs = writer.write_all(result.exchange, trade_date, instruments, rankings, totals)
    database = Database(Path(db_file) if db_file else DEFAULT_DB_PATH)
    database.initialize()
    importer = CsvImporter(database)
    counts = importer.import_trade_date(result.exchange, trade_date)
    print(f"Downloaded: {result.file_path}")
    for name, path in outputs.items():
        print(f"Wrote {name}: {path}")
    for table_name, count in counts.items():
        print(f"Imported {table_name}: {count}")
    return True


def parse_existing_file(exchange: str, file_path: str, trade_date: str | None = None) -> int:
    path = Path(file_path)
    if exchange == "czce":
        instruments, rankings, totals = parse_czce_file(path, exchange=exchange)
        target_date = trade_date or (instruments[0].trade_date if instruments else path.stem)
    elif exchange == "dce":
        instruments, rankings, totals = parse_dce_zip(path, exchange=exchange)
        target_date = trade_date or (instruments[0].trade_date if instruments else path.stem)
    elif exchange == "shfe":
        instruments, rankings, totals = parse_shfe_file(path, exchange=exchange)
        target_date = trade_date or (instruments[0].trade_date if instruments else path.stem)
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")

    writer = CsvWriter()
    outputs = writer.write_all(exchange, target_date, instruments, rankings, totals)
    print(f"Parsed existing file: {path}")
    for name, output_path in outputs.items():
        print(f"Wrote {name}: {output_path}")
    return 0


def run_czce_backfill_range(start_date: str, end_date: str, db_file: str | None = None) -> int:
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    if start < end:
        raise ValueError(f"start_date must be >= end_date, got {start_date} < {end_date}")

    success_count = 0
    skipped_count = 0
    current = start
    while current >= end:
        trade_date = current.strftime("%Y%m%d")
        if current.weekday() >= 5:
            print(f"Skipping weekend: {trade_date}")
            skipped_count += 1
            current -= timedelta(days=1)
            continue

        print(f"Processing {trade_date}...")
        if process_trade_date("czce", trade_date, db_file=db_file):
            success_count += 1
        else:
            skipped_count += 1
        current -= timedelta(days=1)

    print(f"Backfill completed. Imported: {success_count}, skipped: {skipped_count}")
    return 0


def poll_until_found(exchange: str, trade_date: str, once: bool = False, skip_time_window: bool = False, db_file: str | None = None) -> int:
    while True:
        now = datetime.now(TIMEZONE)
        if not skip_time_window and now.hour < POLL_START_HOUR:
            print(f"Waiting until {POLL_START_HOUR}:00 before polling. Current time: {now:%Y-%m-%d %H:%M:%S}")
            return 1

        if now.weekday() >= 5:
            print(f"Skipping non-trading day: {trade_date}")
            return 1

        if process_trade_date(exchange, trade_date, db_file=db_file):
            return 0

        if once or now.hour >= POLL_END_HOUR:
            return 1

        print(f"Retrying in {POLL_INTERVAL_MINUTES} minutes...")
        time.sleep(POLL_INTERVAL_MINUTES * 60)


def serve_web(db_file: str | None = None) -> int:
    from futures_seat_tracker.web.app import create_app

    app = create_app(Path(db_file) if db_file else DEFAULT_DB_PATH)
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
    return 0


def init_database(db_file: str | None = None) -> int:
    database = Database(Path(db_file) if db_file else DEFAULT_DB_PATH)
    database.initialize()
    print(f"Initialized database: {database.db_path}")
    return 0


def import_csv(exchange: str, trade_date: str, db_file: str | None = None) -> int:
    database = Database(Path(db_file) if db_file else DEFAULT_DB_PATH)
    database.initialize()
    importer = CsvImporter(database)
    counts = importer.import_trade_date(exchange, trade_date)
    print(f"Imported parsed CSV for {exchange} {trade_date} into: {database.db_path}")
    for table_name, count in counts.items():
        print(f"Imported {table_name}: {count}")
    return 0


def show_dominant_contract(exchange: str, trade_date: str, product_code: str, db_file: str | None = None) -> int:
    database_path = Path(db_file) if db_file else DEFAULT_DB_PATH
    normalized_product_code = product_code.upper()
    dominant = get_dominant_contract(database_path, exchange, trade_date, normalized_product_code)
    candidates = get_dominant_contract_candidates(database_path, exchange, trade_date, normalized_product_code)
    if dominant is None:
        print(f"No dominant contract candidates found for {exchange} {trade_date} {product_code}")
        return 1

    print(f"Dominant contract for {exchange} {trade_date} {normalized_product_code}: {dominant.contract_code}")
    for candidate in candidates:
        print(
            f"#{candidate.dominance_rank} {candidate.contract_code} "
            f"volume={candidate.volume_total} "
            f"long={candidate.long_open_interest_total} "
            f"short={candidate.short_open_interest_total} "
            f"open_interest={candidate.open_interest_total}"
        )
    return 0


def show_dominant_switches(
    exchange: str,
    product_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
    db_file: str | None = None,
) -> int:
    database_path = Path(db_file) if db_file else DEFAULT_DB_PATH
    normalized_product_code = product_code.upper()
    snapshots, switches = get_dominant_switches(
        database_path,
        exchange,
        normalized_product_code,
        start_date=start_date,
        end_date=end_date,
    )
    if not snapshots:
        print(f"No dominant contract history found for {exchange} {product_code}")
        return 1

    print(f"Dominant contract series for {exchange} {normalized_product_code}:")
    for snapshot in snapshots:
        print(
            f"{snapshot.trade_date} {snapshot.dominant_contract} "
            f"volume={snapshot.volume_total} open_interest={snapshot.open_interest_total}"
        )

    if not switches:
        print("No dominant contract switches detected")
        return 0

    print("Switch events:")
    for switch in switches:
        print(
            f"{switch.prev_trade_date} -> {switch.trade_date}: "
            f"{switch.prev_contract_code} -> {switch.next_contract_code} "
            f"volume {switch.prev_volume_total}->{switch.next_volume_total} "
            f"open_interest {switch.prev_open_interest_total}->{switch.next_open_interest_total}"
        )
    return 0


def main() -> int:
    args = parse_args()
    trade_date = get_trade_date(getattr(args, "date", None))

    if args.command == "parse":
        return parse_existing_file(args.exchange, args.file, trade_date=getattr(args, "date", None))

    if args.command == "backfill":
        return 0 if process_trade_date(args.exchange, trade_date, db_file=getattr(args, "db_file", None)) else 1

    if args.command == "poll":
        return poll_until_found(
            args.exchange,
            trade_date,
            once=args.once,
            skip_time_window=args.skip_time_window,
            db_file=getattr(args, "db_file", None),
        )

    if args.command == "czce-backfill-range":
        return run_czce_backfill_range(
            args.start_date,
            args.end_date,
            db_file=getattr(args, "db_file", None),
        )

    if args.command == "init-db":
        return init_database(getattr(args, "db_file", None))

    if args.command == "import-csv":
        return import_csv(args.exchange, trade_date, db_file=getattr(args, "db_file", None))

    if args.command == "serve":
        return serve_web(getattr(args, "db_file", None))

    if args.command == "dominant-contract":
        return show_dominant_contract(
            args.exchange,
            trade_date,
            args.product,
            db_file=getattr(args, "db_file", None),
        )

    if args.command == "dominant-switch":
        return show_dominant_switches(
            args.exchange,
            args.product,
            start_date=getattr(args, "start_date", None),
            end_date=getattr(args, "end_date", None),
            db_file=getattr(args, "db_file", None),
        )

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
