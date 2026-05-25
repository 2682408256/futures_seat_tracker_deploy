from __future__ import annotations

import re
from pathlib import Path

from futures_seat_tracker.models import DailyMarketRecord

DATE_PATTERN = re.compile(r"(\d{8})")
CONTRACT_PATTERN = re.compile(r"(?P<product>[a-zA-Z]+)(?P<month>\d+)")
DATE_LINE_PATTERN = re.compile(r"大连商品交易所[^\d]*(\d{8})")


def parse_dce_daily_file(file_path: Path, exchange: str = "dce") -> list[DailyMarketRecord]:
    text = _read_text(file_path)
    trade_date = _extract_trade_date(text)
    if not trade_date:
        raise ValueError(f"无法从文件识别交易日：{file_path}")

    lines = text.splitlines()
    header_line = _find_header(lines)
    if header_line < 0:
        raise ValueError("未找到大商所日行情表头")

    header = [col.strip() for col in lines[header_line].split("\t")]
    column_map = _build_column_map(header)
    records: list[DailyMarketRecord] = []
    product_name_map: dict[str, str] = {}
    last_product_name = ""

    for line in lines[header_line + 1:]:
        if not line.strip():
            continue
        cols = [col.strip() for col in line.split("\t")]
        if len(cols) < max(column_map.values(), default=0) + 1:
            continue
        name_val = _get(cols, column_map, "product_name")
        contract_val = _get(cols, column_map, "contract_code")

        if name_val:
            last_product_name = name_val
        if not contract_val or _is_subtotal(cols, column_map):
            if name_val:
                product_name_map[last_product_name] = name_val
            continue

        contract_code = contract_val.lower()
        product_code = _extract_product_code(contract_code)
        product_name = last_product_name or _normalize_product_name(product_code)

        close_change = _parse_float(_get(cols, column_map, "close_change"))
        settlement_change = _parse_float(_get(cols, column_map, "settlement_change"))
        records.append(
            DailyMarketRecord(
                trade_date=trade_date,
                exchange=exchange,
                product_code=product_code,
                product_name=product_name,
                contract_code=contract_code,
                open_price=_parse_float(_get(cols, column_map, "open_price")),
                high_price=_parse_float(_get(cols, column_map, "high_price")),
                low_price=_parse_float(_get(cols, column_map, "low_price")),
                close_price=_parse_float(_get(cols, column_map, "close_price")),
                settlement_price=_parse_float(_get(cols, column_map, "settlement_price")),
                previous_settlement_price=_parse_float(_get(cols, column_map, "previous_settlement_price")),
                change_value=close_change,
                close_change=close_change,
                settlement_change=settlement_change,
                change_pct=_parse_float(_get(cols, column_map, "change_pct")),
                volume=_parse_int(_get(cols, column_map, "volume")),
                open_interest=_parse_int(_get(cols, column_map, "open_interest")),
                open_interest_change=_parse_int(_get(cols, column_map, "open_interest_change")),
                turnover=_parse_float(_get(cols, column_map, "turnover")),
                source_file=file_path.name,
            )
        )

    if not records:
        raise ValueError(f"未从大商所日行情文件解析到数据：{file_path}")
    return records


def _read_text(file_path: Path) -> str:
    data = file_path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_trade_date(text: str) -> str:
    match = DATE_PATTERN.search(text[:200])
    if match:
        return match.group(1)
    return ""


def _find_header(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        cols = [c.strip() for c in line.split("\t")]
        joined = "".join(cols)
        if "合约" in joined and "开盘" in joined and "成交量" in joined:
            return i
    return -1


def _build_column_map(header: list[str]) -> dict[str, int]:
    aliases = {
        "product_name": ["品种名称"],
        "contract_code": ["合约"],
        "open_price": ["开盘价"],
        "high_price": ["最高价"],
        "low_price": ["最低价"],
        "close_price": ["收盘价"],
        "previous_settlement_price": ["前结算价"],
        "settlement_price": ["结算价"],
        "close_change": ["涨跌"],
        "settlement_change": ["涨跌1"],
        "change_pct": ["涨跌幅"],
        "volume": ["成交量"],
        "open_interest": ["持仓量"],
        "open_interest_change": ["持仓量变化"],
        "turnover": ["成交额"],
    }
    result: dict[str, int] = {}
    for field, names in aliases.items():
        for name in names:
            for i, col in enumerate(header):
                if col == name:
                    result[field] = i
                    break
            if field in result:
                break
    if "contract_code" not in result:
        raise ValueError("缺少合约列")
    return result


def _get(cols: list[str], column_map: dict[str, int], field: str) -> str:
    idx = column_map.get(field)
    if idx is None or idx >= len(cols):
        return ""
    return cols[idx]


def _is_subtotal(cols: list[str], column_map: dict[str, int]) -> bool:
    name = _get(cols, column_map, "product_name")
    return bool(name) and "小计" in name


def _extract_product_code(contract_code: str) -> str:
    match = CONTRACT_PATTERN.match(contract_code)
    return match.group("product").upper() if match else contract_code.upper()


def _normalize_product_name(product_code: str) -> str:
    from futures_seat_tracker.web.queries import DCE_PRODUCT_NAMES
    return DCE_PRODUCT_NAMES.get(product_code.upper(), product_code)


def _parse_float(value: str) -> float:
    cleaned = value.replace(",", "").strip()
    if cleaned in {"", "-", "--"}:
        return 0.0
    return float(cleaned)


def _parse_int(value: str) -> int:
    return int(_parse_float(value))