from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from futures_seat_tracker.storage.db import Database


@dataclass(frozen=True)
class DominantContractCandidate:
    contract_code: str
    volume_total: int
    long_open_interest_total: int
    short_open_interest_total: int
    open_interest_total: int
    dominance_rank: int


def get_dominant_contract_candidates(
    db_path: Path,
    exchange: str,
    trade_date: str,
    product_code: str,
) -> list[DominantContractCandidate]:
    if exchange == "czce":
        raise ValueError("CZCE 当前是品种层数据，暂不支持合约主力识别")

    normalized_date = _normalize_trade_date(trade_date)
    normalized_product_code = product_code.upper()
    query_field = "product_name" if exchange == "dce" else "product_code"
    database = Database(db_path)
    with database.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                contract_code,
                MAX(CASE WHEN ranking_type = 'volume' THEN total_value END) AS volume_total,
                MAX(CASE WHEN ranking_type = 'long_open_interest' THEN total_value END) AS long_open_interest_total,
                MAX(CASE WHEN ranking_type = 'short_open_interest' THEN total_value END) AS short_open_interest_total
            FROM totals
            WHERE trade_date = ?
              AND exchange = ?
              AND {query_field} = ?
              AND contract_code != ''
            GROUP BY contract_code
            ORDER BY volume_total DESC,
                     (COALESCE(long_open_interest_total, 0) + COALESCE(short_open_interest_total, 0)) DESC,
                     contract_code ASC
            """,
            (normalized_date, exchange, normalized_product_code),
        ).fetchall()

    candidates: list[DominantContractCandidate] = []
    for index, row in enumerate(rows, start=1):
        long_total = int(row[2] or 0)
        short_total = int(row[3] or 0)
        candidates.append(
            DominantContractCandidate(
                contract_code=str(row[0]),
                volume_total=int(row[1] or 0),
                long_open_interest_total=long_total,
                short_open_interest_total=short_total,
                open_interest_total=long_total + short_total,
                dominance_rank=index,
            )
        )
    return candidates


def get_dominant_contract(
    db_path: Path,
    exchange: str,
    trade_date: str,
    product_code: str,
) -> DominantContractCandidate | None:
    candidates = get_dominant_contract_candidates(db_path, exchange, trade_date, product_code)
    if not candidates:
        return None
    return candidates[0]


def _normalize_trade_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value
