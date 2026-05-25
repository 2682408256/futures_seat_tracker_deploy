from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DownloadResult:
    exchange: str
    trade_date: str
    source_url: str
    file_path: Path
    found: bool


@dataclass(frozen=True)
class InstrumentRecord:
    trade_date: str
    exchange: str
    product_code: str
    product_name: str
    raw_title: str
    contract_code: str = ""
    source_file: str = ""


@dataclass(frozen=True)
class RankingRecord:
    trade_date: str
    exchange: str
    product_code: str
    product_name: str
    ranking_type: str
    rank: int
    member_name: str
    value: int
    change_value: int
    contract_code: str = ""
    source_file: str = ""


@dataclass(frozen=True)
class TotalRecord:
    trade_date: str
    exchange: str
    product_code: str
    product_name: str
    ranking_type: str
    total_value: int
    total_change_value: int
    contract_code: str = ""
    source_file: str = ""


@dataclass(frozen=True)
class DailyMarketRecord:
    trade_date: str
    exchange: str
    product_code: str
    product_name: str
    contract_code: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    settlement_price: float
    previous_settlement_price: float
    change_value: float
    close_change: float
    settlement_change: float
    change_pct: float
    volume: int
    open_interest: int
    open_interest_change: int = 0
    turnover: float = 0.0
    source_file: str = ""
