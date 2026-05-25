from __future__ import annotations

import re
from pathlib import Path

from futures_seat_tracker.models import DailyMarketRecord

DATE_IN_FILENAME = re.compile(r"(\d{8})")
DATE_IN_HEADER = re.compile(r"(?<!\d)(\d{4})(?:[-/年])(\d{1,2})(?:[-/月])(\d{1,2})日?(?!\d)")
CONTRACT_PATTERN = re.compile(r"(?P<month>\d+)(?P<suffix>[a-zA-Z]*)$")

PRODUCT_NAME_MAP: dict[str, str] = {
    "铜": "CU",
    "铝": "AL",
    "锌": "ZN",
    "铅": "PB",
    "镍": "NI",
    "锡": "SN",
    "螺纹钢": "RB",
    "线材": "WR",
    "热轧卷板": "HC",
    "不锈钢": "SS",
    "燃料油": "FU",
    "石油沥青": "BU",
    "天然橡胶": "RU",
    "纸浆": "SP",
    "黄金": "AU",
    "白银": "AG",
    "原油": "SC",
    "原油TAS": "SC_TAS",
    "铜(BC)": "BC",
    "低硫燃料油": "LU",
    "20号胶": "NR",
    "丁二烯橡胶": "BR",
    "铸造铝合金": "AD",
    "氧化铝": "AO",
    "胶版印刷纸": "OP",
    "SCFIS欧线": "EC",
    "SCFIS欧线期货": "EC",
}


def parse_shfe_daily_file(file_path: Path, exchange: str = "shfe") -> list[DailyMarketRecord]:
    text = _read_text(file_path)
    trade_date = _extract_trade_date(text) or _extract_date_from_filename(file_path.name)
    if not trade_date:
        raise ValueError(f"无法识别交易日，请确认文件名包含日期或上传时填写日期：{file_path}")

    lines = text.splitlines()
    records: list[DailyMarketRecord] = []
    current_product_name = ""
    current_product_code = ""

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("注：") or stripped.startswith("上海期货"):
            continue

        if "商品名称:" in stripped:
            raw_name = stripped.split("商品名称:", 1)[1].strip().rstrip(",")
            current_product_name = raw_name
            current_product_code = PRODUCT_NAME_MAP.get(raw_name, _normalize_code(raw_name))
            continue

        cols = [c.strip() for c in stripped.split(",")]
        if len(cols) < 12:
            continue

        if cols[0].isdigit():
            contract_code = cols[0]
            if len(contract_code) < 4:
                continue

            prev_settle = _parse_float(cols[1])
            close_price = _parse_float(cols[5])
            settlement_price = _parse_float(cols[6])
            prev_settle_used = prev_settle if prev_settle > 0 else settlement_price
            close_change = _parse_float(cols[7])
            settlement_change = _parse_float(cols[8])
            volume = _parse_int(cols[9])
            turnover_wan = _parse_float(cols[10])
            open_interest = _parse_int(cols[11])
            open_interest_change = _parse_int(cols[12]) if len(cols) > 12 else 0

            normalized_contract_code = f"{current_product_code.lower()}{contract_code}"
            records.append(
                DailyMarketRecord(
                    trade_date=trade_date,
                    exchange=exchange,
                    product_code=current_product_code,
                    product_name=current_product_name,
                    contract_code=normalized_contract_code,
                    open_price=_parse_float(cols[2]),
                    high_price=_parse_float(cols[3]),
                    low_price=_parse_float(cols[4]),
                    close_price=close_price,
                    settlement_price=settlement_price,
                    previous_settlement_price=prev_settle_used,
                    change_value=close_change,
                    close_change=close_change,
                    settlement_change=settlement_change,
                    change_pct=0.0,
                    volume=volume,
                    open_interest=open_interest,
                    open_interest_change=open_interest_change,
                    turnover=turnover_wan * 10000,
                    source_file=file_path.name,
                )
            )

    if not records:
        raise ValueError(f"未从上期所日行情文件解析到数据：{file_path}")
    return records


def _read_text(file_path: Path) -> str:
    data = file_path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_trade_date(text: str) -> str | None:
    header_match = DATE_IN_HEADER.search(text)
    if header_match:
        year, month, day = header_match.groups()
        return f"{year}{int(month):02d}{int(day):02d}"
    match = DATE_IN_FILENAME.search(text[:300])
    if match:
        raw = match.group(1)
        if len(raw) == 8:
            return raw
    return None


def _extract_date_from_filename(filename: str) -> str | None:
    match = DATE_IN_FILENAME.search(filename)
    if match:
        raw = match.group(1)
        if len(raw) == 8:
            return raw
    return None


def _normalize_code(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw)
    return cleaned.upper()[:4]


def _parse_float(value: str) -> float:
    cleaned = value.strip().replace(",", "")
    if cleaned in {"", "-", "--", "?"}:
        return 0.0
    return float(cleaned)


def _parse_int(value: str) -> int:
    return int(_parse_float(value))
