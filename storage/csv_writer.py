from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from futures_seat_tracker.config import PARSED_DIR
from futures_seat_tracker.models import InstrumentRecord, RankingRecord, TotalRecord


class CsvWriter:
    def build_output_dir(self, exchange: str, trade_date: str) -> Path:
        year = trade_date[:4]
        return PARSED_DIR / exchange / year / trade_date

    def write_all(
        self,
        exchange: str,
        trade_date: str,
        instruments: Iterable[InstrumentRecord],
        rankings: Iterable[RankingRecord],
        totals: Iterable[TotalRecord],
    ) -> dict[str, Path]:
        output_dir = self.build_output_dir(exchange, trade_date)
        output_dir.mkdir(parents=True, exist_ok=True)

        instrument_path = output_dir / "instruments.csv"
        ranking_path = output_dir / "rankings.csv"
        total_path = output_dir / "totals.csv"

        self.write_csv(instrument_path, instruments)
        self.write_csv(ranking_path, rankings)
        self.write_csv(total_path, totals)

        return {
            "instruments": instrument_path,
            "rankings": ranking_path,
            "totals": total_path,
        }

    def write_csv(self, file_path: Path, rows: Iterable[object]) -> None:
        rows = list(rows)
        if not rows:
            return

        fieldnames = list(asdict(rows[0]).keys())
        with file_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))

