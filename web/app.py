from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, abort, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from futures_seat_tracker.config import DEFAULT_DB_PATH, POLL_INTERVAL_MINUTES, POLL_START_HOUR, RAW_DIR
from futures_seat_tracker.main import process_trade_date
from futures_seat_tracker.parsers.dce import parse_dce_zip
from futures_seat_tracker.parsers.shfe import parse_shfe_file
from futures_seat_tracker.storage.csv_writer import CsvWriter
from futures_seat_tracker.storage.db import Database
from futures_seat_tracker.storage.importer import CsvImporter
from futures_seat_tracker.web.queries import DashboardQueries

TIMEZONE = ZoneInfo("Asia/Shanghai")
UPLOAD_SPECS = {
    "dce": {
        "label": "大商所",
        "extensions": {".zip"},
    },
    "shfe": {
        "label": "上期所",
        "extensions": {".txt"},
    },
}


def create_app(db_path: Path | None = None, start_polling: bool = True) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    database_path = db_path or DEFAULT_DB_PATH
    queries = DashboardQueries(database_path)
    if start_polling:
        _start_czce_polling(database_path)

    @app.route("/")
    def index() -> str:
        search = request.args.get("q", "")
        items = queries.list_dominant_contracts(search=search)
        return render_template(
            "index.html",
            items=items,
            search=search,
            item_count=len(items),
            message=request.args.get("message", ""),
            message_level=request.args.get("level", "success"),
            upload_specs=UPLOAD_SPECS,
            czce_polling_summary=_build_czce_polling_summary(),
        )

    @app.post("/upload/<exchange>")
    def upload_exchange_file(exchange: str):
        upload_spec = UPLOAD_SPECS.get(exchange)
        if upload_spec is None:
            abort(404)

        uploaded_files = request.files.getlist("files")
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return _redirect_with_message("请选择要上传的文件。", "error")

        results: list[tuple[str, str]] = []
        errors: list[str] = []
        for uploaded_file in uploaded_files:
            if not uploaded_file.filename:
                continue

            original_name = Path(uploaded_file.filename).name
            extension = Path(original_name).suffix.lower()
            if extension not in upload_spec["extensions"]:
                errors.append(f"{original_name}：仅支持 {'、'.join(sorted(upload_spec['extensions']))} 文件，已跳过。")
                continue

            timestamp = datetime.now(TIMEZONE).strftime("%Y%m%d%H%M%S")
            safe_name = secure_filename(original_name) or f"{exchange}{extension}"
            target_dir = RAW_DIR / exchange / "uploads"
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / f"{timestamp}_{safe_name}"
            uploaded_file.save(file_path)

            try:
                imported_trade_date = _import_uploaded_file(exchange, file_path, None, database_path)
                results.append((original_name, imported_trade_date))
            except ValueError as exc:
                errors.append(f"{original_name}：{exc}")
                if file_path.exists():
                    file_path.unlink()
            except Exception:
                errors.append(f"{original_name}：处理失败，已跳过。")
                if file_path.exists():
                    file_path.unlink()

        if not results and errors:
            return _redirect_with_message("；".join(errors), "error")

        messages = [f"{name} → {date}" for name, date in results]
        if errors:
            messages.extend(errors)
        return _redirect_with_message("，".join(messages), "success" if not errors else "warning")

    @app.route("/contract/<exchange>/<product_code>")
    def contract_detail(exchange: str, product_code: str) -> str:
        trade_date = request.args.get("date")
        if not trade_date:
            items = [item for item in queries.list_dominant_contracts() if item.exchange == exchange and item.product_code == product_code]
            if not items:
                abort(404)
            trade_date = items[0].trade_date
        detail = queries.get_contract_detail(exchange, product_code, trade_date)
        if detail is None:
            abort(404)
        return render_template("contract_detail.html", detail=detail)

    return app


def _import_uploaded_file(exchange: str, file_path: Path, trade_date: str | None, db_path: Path) -> str:
    target_trade_date, instruments, rankings, totals = _parse_exchange_file(exchange, file_path)
    writer = CsvWriter()
    writer.write_all(exchange, target_trade_date, instruments, rankings, totals)
    database = Database(db_path)
    database.initialize()
    importer = CsvImporter(database)
    importer.import_trade_date(exchange, target_trade_date)
    return target_trade_date


def _parse_exchange_file(exchange: str, file_path: Path) -> tuple[str, list, list, list]:
    if exchange == "dce":
        instruments, rankings, totals = parse_dce_zip(file_path, exchange=exchange)
    elif exchange == "shfe":
        instruments, rankings, totals = parse_shfe_file(file_path, exchange=exchange)
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")

    target_trade_date = instruments[0].trade_date if instruments else ""
    if not target_trade_date:
        raise ValueError("文件解析失败，未识别到交易日。")
    if not instruments:
        raise ValueError("文件解析失败，请确认上传的是交易所原始文件。")
    return target_trade_date, instruments, rankings, totals


def _import_batch(exchange: str, file_paths: list[Path], db_path: Path) -> list[tuple[Path, str]]:
    results: list[tuple[Path, str]] = []
    for file_path in file_paths:
        try:
            target_trade_date, instruments, rankings, totals = _parse_exchange_file(exchange, file_path)
            writer = CsvWriter()
            writer.write_all(exchange, target_trade_date, instruments, rankings, totals)
            database = Database(db_path)
            database.initialize()
            importer = CsvImporter(database)
            importer.import_trade_date(exchange, target_trade_date)
            results.append((file_path, target_trade_date))
        except Exception:
            pass
    return results


def _start_czce_polling(db_path: Path) -> None:
    if getattr(_start_czce_polling, "started", False):
        return
    worker = threading.Thread(target=_run_czce_polling_loop, args=(db_path,), daemon=True)
    worker.start()
    _start_czce_polling.started = True


def _run_czce_polling_loop(db_path: Path) -> None:
    last_completed_trade_date = ""
    while True:
        now = datetime.now(TIMEZONE)
        trade_date = now.strftime("%Y%m%d")

        if trade_date == last_completed_trade_date:
            time.sleep(600)
            continue

        if now.hour < POLL_START_HOUR:
            time.sleep(300)
            continue

        if process_trade_date("czce", trade_date, db_file=str(db_path)):
            last_completed_trade_date = trade_date
            time.sleep(600)
            continue

        time.sleep(POLL_INTERVAL_MINUTES * 60)


def _build_czce_polling_summary() -> str:
    return f"郑商所每日 {POLL_START_HOUR}:00 后每 {POLL_INTERVAL_MINUTES} 分钟自动查询，抓到数据后自动解析入库。"


def _redirect_with_message(message: str, level: str):
    return redirect(url_for("index", message=message, level=level))
