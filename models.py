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
