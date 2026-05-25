from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from futures_seat_tracker.storage.db import Database


CZCE_DAILY_PRODUCT_ALIASES = {
    "PTA": "TA",
}


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
    normalized_date = _normalize_trade_date(trade_date)
    normalized_product_code = product_code.upper()
    daily_product_codes = _daily_product_codes(exchange, normalized_product_code)
    query_field = "product_name" if exchange == "dce" else "product_code"
    database = Database(db_path)
    with database.connect() as connection:
        placeholders = ", ".join("?" for _ in daily_product_codes)
        rows = connection.execute(
            f"""
            SELECT contract_code, volume, open_interest, 0
            FROM daily_markets
            WHERE trade_date = ?
              AND exchange = ?
              AND (product_code IN ({placeholders}) OR product_name = ?)
              AND contract_code != ''
            ORDER BY volume DESC, open_interest DESC, contract_code ASC
            """,
            (normalized_date, exchange, *daily_product_codes, product_code),
        ).fetchall()
        if not rows:
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


def _daily_product_codes(exchange: str, product_code: str) -> list[str]:
    codes = [product_code]
    if exchange == "czce":
        alias = CZCE_DAILY_PRODUCT_ALIASES.get(product_code)
        if alias:
            codes.append(alias)
    return codes
