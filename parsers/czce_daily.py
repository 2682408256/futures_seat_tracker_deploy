from __future__ import annotations

import re
from pathlib import Path

from futures_seat_tracker.models import DailyMarketRecord

DATE_PATTERN = re.compile(r"(?P<year>\d{4})[-/]?(?P<month>\d{2})[-/]?(?P<day>\d{2})")
CONTRACT_PATTERN = re.compile(r"(?P<product>[A-Za-z]+)(?P<month>\d+)")

FIELD_ALIASES = {
    "contract_code": ("合约代码", "合约", "品种月份", "品种代码"),
    "product_name": ("品种名称", "品种"),
    "previous_settlement_price": ("昨结算", "昨结算价", "上日结算价"),
    "open_price": ("今开盘", "开盘价", "开盘"),
    "high_price": ("最高价", "最高"),
    "low_price": ("最低价", "最低"),
    "close_price": ("今收盘", "收盘价", "收盘"),
    "settlement_price": ("今结算", "结算价", "结算"),
    "close_change": ("涨跌", "涨跌1", "涨跌额"),
    "settlement_change": ("涨跌2", "涨跌二"),
    "change_pct": ("涨跌幅", "涨跌幅%"),
    "volume": ("成交量",),
    "open_interest": ("空盘量", "持仓量", "持仓"),
}


def parse_czce_daily_file(file_path: Path, trade_date: str, exchange: str = "czce") -> list[DailyMarketRecord]:
    text = _read_text(file_path)
    target_trade_date = _extract_trade_date(text) or trade_date
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_index, header = _find_header(lines)
    column_map = _build_column_map(header)
    records: list[DailyMarketRecord] = []

    for line in lines[header_index + 1:]:
        columns = _split_columns(line)
        if len(columns) < 4 or _is_non_data_row(columns):
            continue
        contract_code = _get(columns, column_map, "contract_code").upper()
        if not contract_code or not CONTRACT_PATTERN.match(contract_code):
            continue
        product_code = _extract_product_code(contract_code)
        product_name = _get(columns, column_map, "product_name") or product_code
        close_price = _parse_float(_get(columns, column_map, "close_price"))
        settlement_price = _parse_float(_get(columns, column_map, "settlement_price"))
        previous_settlement_price = _parse_float(_get(columns, column_map, "previous_settlement_price"))
        close_change = _parse_float(_get(columns, column_map, "close_change")) or close_price - previous_settlement_price
        settlement_change = _parse_float(_get(columns, column_map, "settlement_change")) or settlement_price - previous_settlement_price
        records.append(
            DailyMarketRecord(
                trade_date=target_trade_date,
                exchange=exchange,
                product_code=product_code,
                product_name=product_name,
                contract_code=contract_code,
                open_price=_parse_float(_get(columns, column_map, "open_price")),
                high_price=_parse_float(_get(columns, column_map, "high_price")),
                low_price=_parse_float(_get(columns, column_map, "low_price")),
                close_price=close_price,
                settlement_price=settlement_price,
                previous_settlement_price=previous_settlement_price,
                change_value=close_change,
                close_change=close_change,
                settlement_change=settlement_change,
                change_pct=_parse_float(_get(columns, column_map, "change_pct")),
                volume=_parse_int(_get(columns, column_map, "volume")),
                open_interest=_parse_int(_get(columns, column_map, "open_interest")),
                source_file=file_path.name,
            )
        )

    if not records:
        raise ValueError(f"未从郑商所日行情文件解析到数据：{file_path}")
    return records


def _read_text(file_path: Path) -> str:
    data = file_path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_trade_date(text: str) -> str:
    match = DATE_PATTERN.search(text[:500])
    if not match:
        return ""
    return f"{match.group('year')}{match.group('month')}{match.group('day')}"


def _find_header(lines: list[str]) -> tuple[int, list[str]]:
    for index, line in enumerate(lines):
        columns = _split_columns(line)
        joined = "".join(columns)
        if "合约" in joined and ("开盘" in joined or "今开盘" in joined) and "成交量" in joined:
            return index, columns
    raise ValueError("未识别到郑商所日行情表头")


def _split_columns(line: str) -> list[str]:
    if "|" in line:
        columns = [part.strip() for part in line.split("|")]
    elif "," in line:
        columns = [part.strip() for part in line.split(",")]
    else:
        columns = re.split(r"\s+", line.strip())
    return [column for column in columns if column]


def _build_column_map(header: list[str]) -> dict[str, int]:
    normalized = [_normalize_header(column) for column in header]
    result: dict[str, int] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            target = _normalize_header(alias)
            for index, column in enumerate(normalized):
                if target == column or target in column:
                    result[field] = index
                    break
            if field in result:
                break
    if "contract_code" not in result:
        raise ValueError("郑商所日行情缺少合约代码列")
    return result


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s：:()（）%]", "", value)


def _get(columns: list[str], column_map: dict[str, int], field: str) -> str:
    index = column_map.get(field)
    if index is None or index >= len(columns):
        return ""
    return columns[index].strip()


def _is_non_data_row(columns: list[str]) -> bool:
    first = columns[0]
    return first in {"合计", "小计"} or "说明" in first or "备注" in first


def _extract_product_code(contract_code: str) -> str:
    match = CONTRACT_PATTERN.match(contract_code)
    return match.group("product").upper() if match else contract_code.upper()


def _parse_float(value: str) -> float:
    cleaned = value.replace(",", "").replace("%", "").strip()
    if cleaned in {"", "-", "--"}:
        return 0.0
    return float(cleaned)


def _parse_int(value: str) -> int:
    return int(_parse_float(value))
