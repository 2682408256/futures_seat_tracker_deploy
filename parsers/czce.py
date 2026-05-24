from __future__ import annotations

import re
from pathlib import Path

from futures_seat_tracker.models import InstrumentRecord, RankingRecord, TotalRecord

SECTION_PATTERN = re.compile(
    r"品种：(?P<title>.+?)\s+日期：(?P<trade_date>\d{4}-\d{2}-\d{2})\n"
    r"(?P<body>.*?)(?=\n\n品种：|\Z)",
    re.S,
)
TITLE_PATTERN = re.compile(r"(?P<product_name>[一-鿿]+)(?P<product_code>[A-Z]+)$")


def parse_number(value: str) -> int:
    cleaned = value.replace(",", "").strip()
    if cleaned in {"", "-"}:
        return 0
    return int(cleaned)



def parse_product_title(title: str) -> tuple[str, str]:
    clean_title = title.strip()
    match = TITLE_PATTERN.match(clean_title)
    if match:
        return match.group("product_name"), match.group("product_code")
    return clean_title, clean_title


def split_columns(line: str) -> list[str]:
    return [part.strip() for part in line.split("|")]


def parse_czce_file(file_path: Path, exchange: str = "czce") -> tuple[list[InstrumentRecord], list[RankingRecord], list[TotalRecord]]:
    text = file_path.read_text(encoding="utf-8")
    instruments: list[InstrumentRecord] = []
    rankings: list[RankingRecord] = []
    totals: list[TotalRecord] = []

    for match in SECTION_PATTERN.finditer(text):
        raw_title = match.group("title").strip()
        trade_date = match.group("trade_date").replace("-", "")
        product_name, product_code = parse_product_title(raw_title)
        body = match.group("body").strip().splitlines()

        instruments.append(
            InstrumentRecord(
                trade_date=trade_date,
                exchange=exchange,
                product_code=product_code,
                product_name=product_name,
                raw_title=raw_title,
                source_file=file_path.name,
            )
        )

        for line in body:
            columns = split_columns(line)
            if not columns or len(columns) < 10:
                continue

            rank_label = columns[0]
            if rank_label in {"名次", "", None}:
                continue

            if rank_label == "合计":
                total_specs = (
                    ("volume", columns[2], columns[3]),
                    ("long_open_interest", columns[5], columns[6]),
                    ("short_open_interest", columns[8], columns[9]),
                )
                for ranking_type, total_value, total_change in total_specs:
                    totals.append(
                        TotalRecord(
                            trade_date=trade_date,
                            exchange=exchange,
                            product_code=product_code,
                            product_name=product_name,
                            ranking_type=ranking_type,
                            total_value=parse_number(total_value),
                            total_change_value=parse_number(total_change),
                            source_file=file_path.name,
                        )
                    )
                continue

            try:
                rank = int(rank_label)
            except ValueError:
                continue

            ranking_specs = (
                ("volume", columns[1], columns[2], columns[3]),
                ("long_open_interest", columns[4], columns[5], columns[6]),
                ("short_open_interest", columns[7], columns[8], columns[9]),
            )
            for ranking_type, member_name, value, change_value in ranking_specs:
                rankings.append(
                    RankingRecord(
                        trade_date=trade_date,
                        exchange=exchange,
                        product_code=product_code,
                        product_name=product_name,
                        ranking_type=ranking_type,
                        rank=rank,
                        member_name=member_name,
                        value=parse_number(value),
                        change_value=parse_number(change_value),
                        source_file=file_path.name,
                    )
                )

    return instruments, rankings, totals
