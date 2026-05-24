from __future__ import annotations

import re
import zipfile
from pathlib import Path

from futures_seat_tracker.models import InstrumentRecord, RankingRecord, TotalRecord

SECTION_HEADER_PATTERN = re.compile(r"^合约代码：(?P<contract_code>\S+)\s+Date：(?P<trade_date>\d{4}-\d{2}-\d{2})$")
TITLE_PATTERN = re.compile(r"^(?P<product_name>[一-鿿]+)(?P<product_code>[A-Z]+)$")


def parse_number(value: str) -> int:
    cleaned = value.replace(",", "").strip()
    if cleaned in {"", "-"}:
        return 0
    return int(cleaned)


def parse_product_code(contract_code: str) -> tuple[str, str]:
    code = contract_code.strip()
    match = re.match(r"(?P<product_name>[a-zA-Z]+)(?P<month>\d+)$", code)
    if match:
        return match.group("product_name").upper(), code.upper()
    return code.upper(), code.upper()


def split_columns(line: str) -> list[str]:
    return [part.strip() for part in line.split("\t") if part.strip()]


def parse_contract_file(text: str, source_file: str, exchange: str = "dce") -> tuple[list[InstrumentRecord], list[RankingRecord], list[TotalRecord]]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return [], [], []

    header = lines[1] if len(lines) > 1 else ""
    match = SECTION_HEADER_PATTERN.match(header)
    if not match:
        return [], [], []

    contract_code = match.group("contract_code")
    trade_date = match.group("trade_date").replace("-", "")
    product_name, product_code = parse_product_code(contract_code)

    instrument = InstrumentRecord(
        trade_date=trade_date,
        exchange=exchange,
        product_code=product_code,
        product_name=product_name,
        raw_title=contract_code,
        contract_code=contract_code,
        source_file=source_file,
    )

    rankings: list[RankingRecord] = []
    totals: list[TotalRecord] = []

    section_type = None
    for line in lines[2:]:
        if line.startswith("名次"):
            if "成交量" in line:
                section_type = "volume"
            elif "持买单量" in line:
                section_type = "long_open_interest"
            elif "持卖单量" in line:
                section_type = "short_open_interest"
            continue

        columns = split_columns(line)
        if not columns:
            continue

        if columns[0] == "合计" and section_type:
            totals.append(
                TotalRecord(
                    trade_date=trade_date,
                    exchange=exchange,
                    product_code=product_code,
                    product_name=product_name,
                    ranking_type=section_type,
                    total_value=parse_number(columns[3] if len(columns) > 3 else columns[-2]),
                    total_change_value=parse_number(columns[4] if len(columns) > 4 else columns[-1]),
                    contract_code=contract_code,
                    source_file=source_file,
                )
            )
            continue

        if not columns[0].isdigit() or not section_type:
            continue

        rank = int(columns[0])
        member_name = columns[1]
        value = parse_number(columns[2])
        change_value = parse_number(columns[3])
        rankings.append(
            RankingRecord(
                trade_date=trade_date,
                exchange=exchange,
                product_code=product_code,
                product_name=product_name,
                ranking_type=section_type,
                rank=rank,
                member_name=member_name,
                value=value,
                change_value=change_value,
                contract_code=contract_code,
                source_file=source_file,
            )
        )

    return [instrument], rankings, totals


def parse_dce_zip(zip_path: Path, exchange: str = "dce") -> tuple[list[InstrumentRecord], list[RankingRecord], list[TotalRecord]]:
    instruments: list[InstrumentRecord] = []
    rankings: list[RankingRecord] = []
    totals: list[TotalRecord] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in sorted(zf.namelist()):
            if not name.lower().endswith(".txt"):
                continue
            content = zf.read(name).decode("utf-8", errors="replace")
            file_instruments, file_rankings, file_totals = parse_contract_file(content, source_file=name, exchange=exchange)
            instruments.extend(file_instruments)
            rankings.extend(file_rankings)
            totals.extend(file_totals)

    return instruments, rankings, totals
