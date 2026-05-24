from __future__ import annotations

from pathlib import Path

from futures_seat_tracker.models import InstrumentRecord, RankingRecord, TotalRecord


def parse_number(value: str) -> int:
    cleaned = value.replace(",", "").strip()
    if cleaned in {"", "-"}:
        return 0
    return int(cleaned)


def parse_contract_parts(contract_code: str) -> tuple[str, str]:
    prefix = ""
    for char in contract_code:
        if char.isalpha():
            prefix += char
        else:
            break
    if prefix:
        return prefix.upper(), contract_code.lower()
    return contract_code.upper(), contract_code.lower()


def split_csv_line(line: str) -> list[str]:
    return [part.strip() for part in line.split(",")]


def parse_shfe_file(file_path: Path, exchange: str = "shfe") -> tuple[list[InstrumentRecord], list[RankingRecord], list[TotalRecord]]:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    instruments: list[InstrumentRecord] = []
    rankings: list[RankingRecord] = []
    totals: list[TotalRecord] = []

    current_product_name = ""
    current_product_code = ""
    current_contract_code = ""
    current_trade_date = ""

    i = 0
    while i < len(lines):
        row = split_csv_line(lines[i].strip())
        if not any(row):
            i += 1
            continue

        first = row[0]

        if first.startswith("商品名称："):
            current_product_name = first.split("：", 1)[1].strip()
            if len(row) > 7 and row[7]:
                current_trade_date = row[7].replace("-", "")
            i += 1
            continue

        if first.startswith("合约代码："):
            raw_contract_code = first.split("：", 1)[1].strip()
            current_product_code, current_contract_code = parse_contract_parts(raw_contract_code)
            if len(row) > 10 and row[10]:
                current_trade_date = row[10].replace("-", "")
            instruments.append(
                InstrumentRecord(
                    trade_date=current_trade_date,
                    exchange=exchange,
                    product_code=current_product_code,
                    product_name=current_product_name,
                    raw_title=raw_contract_code,
                    contract_code=current_contract_code,
                    source_file=file_path.name,
                )
            )

            i += 1
            if i < len(lines):
                header = split_csv_line(lines[i].strip())
                if header and header[0] == "名次":
                    i += 1

            while i < len(lines):
                row = split_csv_line(lines[i].strip())
                if not any(row):
                    i += 1
                    continue

                first = row[0]
                if first.startswith("商品名称：") or first.startswith("合约代码：") or first == "名次":
                    break
                if len(row) < 12:
                    i += 1
                    continue

                section_specs = [
                    ("volume", 1, 2, 3),
                    ("long_open_interest", 5, 6, 7),
                    ("short_open_interest", 9, 10, 11),
                ]

                if first == "合计":
                    for ranking_type, _, value_idx, change_idx in section_specs:
                        totals.append(
                            TotalRecord(
                                trade_date=current_trade_date,
                                exchange=exchange,
                                product_code=current_product_code,
                                product_name=current_product_name,
                                ranking_type=ranking_type,
                                total_value=parse_number(row[value_idx]),
                                total_change_value=parse_number(row[change_idx]),
                                contract_code=current_contract_code,
                                source_file=file_path.name,
                            )
                        )
                elif first.isdigit():
                    rank = int(first)
                    for ranking_type, name_idx, value_idx, change_idx in section_specs:
                        rankings.append(
                            RankingRecord(
                                trade_date=current_trade_date,
                                exchange=exchange,
                                product_code=current_product_code,
                                product_name=current_product_name,
                                ranking_type=ranking_type,
                                rank=rank,
                                member_name=row[name_idx],
                                value=parse_number(row[value_idx]),
                                change_value=parse_number(row[change_idx]),
                                contract_code=current_contract_code,
                                source_file=file_path.name,
                            )
                        )
                i += 1
            continue

        i += 1

    return instruments, rankings, totals

