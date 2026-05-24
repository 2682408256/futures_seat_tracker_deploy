from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from futures_seat_tracker.analysis.dominant_contracts import DominantContractCandidate, get_dominant_contract
from futures_seat_tracker.storage.db import Database


@dataclass(frozen=True)
class DominantContractSnapshot:
    trade_date: str
    dominant_contract: str
    volume_total: int
    open_interest_total: int


@dataclass(frozen=True)
class DominantSwitchEvent:
    trade_date: str
    prev_trade_date: str
    prev_contract_code: str
    next_contract_code: str
    prev_volume_total: int
    next_volume_total: int
    prev_open_interest_total: int
    next_open_interest_total: int


def get_dominant_contract_series(
    db_path: Path,
    exchange: str,
    product_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[DominantContractSnapshot]:
    normalized_product = product_code.upper()
    trade_dates = _get_trade_dates(db_path, exchange, normalized_product, start_date, end_date)
    snapshots: list[DominantContractSnapshot] = []
    for trade_date in trade_dates:
        candidate = get_dominant_contract(db_path, exchange, trade_date, normalized_product)
        if candidate is None:
            continue
        snapshots.append(_to_snapshot(trade_date, candidate))
    return snapshots


def get_dominant_switches(
    db_path: Path,
    exchange: str,
    product_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[DominantContractSnapshot], list[DominantSwitchEvent]]:
    snapshots = get_dominant_contract_series(db_path, exchange, product_code, start_date=start_date, end_date=end_date)
    switches: list[DominantSwitchEvent] = []
    for previous, current in zip(snapshots, snapshots[1:]):
        if previous.dominant_contract == current.dominant_contract:
            continue
        switches.append(
            DominantSwitchEvent(
                trade_date=current.trade_date,
                prev_trade_date=previous.trade_date,
                prev_contract_code=previous.dominant_contract,
                next_contract_code=current.dominant_contract,
                prev_volume_total=previous.volume_total,
                next_volume_total=current.volume_total,
                prev_open_interest_total=previous.open_interest_total,
                next_open_interest_total=current.open_interest_total,
            )
        )
    return snapshots, switches


def _get_trade_dates(
    db_path: Path,
    exchange: str,
    product_code: str,
    start_date: str | None,
    end_date: str | None,
) -> list[str]:
    query_field = "product_name" if exchange == "dce" else "product_code"
    clauses = ["exchange = ?", f"{query_field} = ?", "contract_code != ''"]
    params: list[str] = [exchange, product_code.upper()]
    if start_date:
        clauses.append("trade_date >= ?")
        params.append(_normalize_trade_date(start_date))
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(_normalize_trade_date(end_date))

    database = Database(db_path)
    with database.connect() as connection:
        rows = connection.execute(
            f"select distinct trade_date from totals where {' and '.join(clauses)} order by trade_date",
            params,
        ).fetchall()
    return [str(row[0]) for row in rows]


def _to_snapshot(trade_date: str, candidate: DominantContractCandidate) -> DominantContractSnapshot:
    return DominantContractSnapshot(
        trade_date=trade_date,
        dominant_contract=candidate.contract_code,
        volume_total=candidate.volume_total,
        open_interest_total=candidate.open_interest_total,
    )


def _normalize_trade_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value
