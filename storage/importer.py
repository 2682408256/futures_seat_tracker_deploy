from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from futures_seat_tracker.config import PARSED_DIR
from futures_seat_tracker.storage.db import Database


class CsvImporter:
    def __init__(self, database: Database) -> None:
        self.database = database

    def import_trade_date(self, exchange: str, trade_date: str) -> dict[str, int]:
        input_dir = PARSED_DIR / exchange / trade_date[:4] / trade_date
        return self.import_from_dir(input_dir)

    def import_from_dir(self, input_dir: Path) -> dict[str, int]:
        file_map = {
            "instruments": input_dir / "instruments.csv",
            "rankings": input_dir / "rankings.csv",
            "totals": input_dir / "totals.csv",
        }

        with self.database.connect() as connection:
            counts = {
                table_name: self._import_file(connection, table_name, file_path)
                for table_name, file_path in file_map.items()
            }
            connection.commit()
        return counts

    def _import_file(self, connection, table_name: str, file_path: Path) -> int:
        if not file_path.exists():
            return 0

        with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [self._normalize_row(table_name, row) for row in reader]

        if not rows:
            return 0

        columns = list(rows[0].keys())
        placeholders = ", ".join(f":{column}" for column in columns)
        assignments = ", ".join(
            f"{column} = excluded.{column}"
            for column in columns
            if column not in self._conflict_columns(table_name)
        )
        sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT ({', '.join(self._conflict_columns(table_name))})
            DO UPDATE SET {assignments}
        """
        connection.executemany(sql, rows)
        return len(rows)

    def _normalize_row(self, table_name: str, row: dict[str, str]) -> dict[str, object]:
        normalized = {
            key: (value or "").strip()
            for key, value in row.items()
        }
        normalized["trade_date"] = self._format_trade_date(normalized["trade_date"])
        normalized["contract_code"] = normalized.get("contract_code", "")
        normalized["source_file"] = normalized.get("source_file", "")

        integer_fields = {
            "rankings": ["rank", "value", "change_value"],
            "totals": ["total_value", "total_change_value"],
        }.get(table_name, [])

        for field in integer_fields:
            normalized[field] = int(normalized[field])

        return normalized

    def _format_trade_date(self, value: str) -> str:
        if len(value) == 8 and value.isdigit():
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
        return value

    def _conflict_columns(self, table_name: str) -> Iterable[str]:
        if table_name == "instruments":
            return ["trade_date", "exchange", "product_code", "contract_code", "raw_title"]
        if table_name == "rankings":
            return ["trade_date", "exchange", "product_code", "contract_code", "ranking_type", "rank", "member_name"]
        if table_name == "totals":
            return ["trade_date", "exchange", "product_code", "contract_code", "ranking_type"]
        raise ValueError(f"Unsupported table: {table_name}")
