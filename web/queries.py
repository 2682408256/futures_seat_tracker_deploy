from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from futures_seat_tracker.analysis.dominant_contracts import get_dominant_contract
from futures_seat_tracker.analysis.rollover import get_dominant_switches
from futures_seat_tracker.storage.db import Database

DCE_PRODUCT_NAMES = {
    "A": "豆一",
    "B": "豆二",
    "BZ": "纯苯",
    "C": "玉米",
    "CS": "玉米淀粉",
    "EB": "苯乙烯",
    "EG": "乙二醇",
    "I": "铁矿石",
    "J": "焦炭",
    "JD": "鸡蛋",
    "JM": "焦煤",
    "L": "塑料",
    "LG": "原木",
    "LH": "生猪",
    "M": "豆粕",
    "P": "棕榈油",
    "PG": "LPG",
    "PP": "聚丙烯",
    "RR": "粳米",
    "V": "PVC",
    "Y": "豆油",
}

INSTITUTIONAL_MEMBERS = [
    "东证期货",
    "永安期货",
    "高盛期货",
    "中信期货",
    "国泰君安",
    "瑞银期货",
]

INSTITUTIONAL_MEMBERS_EXCLUDING_DONGZHENG = [
    member for member in INSTITUTIONAL_MEMBERS if member != "东证期货"
]

RETAIL_MEMBERS = [
    "徽商期货",
    "东方财富",
    "平安期货",
    "中信建投",
]


@dataclass(frozen=True)
class ContractIndexItem:
    exchange: str
    product_code: str
    product_name: str
    trade_date: str
    contract_code: str


@dataclass(frozen=True)
class ContractNavItem:
    exchange: str
    product_code: str
    product_name: str
    trade_date: str
    contract_code: str


@dataclass(frozen=True)
class MemberNetRow:
    member_label: str
    matched_member_names: list[str]
    net_position: int
    net_change: int
    long_value: int
    short_value: int
    long_change: int
    short_change: int


@dataclass(frozen=True)
class ContractDetailData:
    exchange: str
    product_code: str
    product_name: str
    trade_date: str
    contract_code: str
    available_dates: list[str]
    previous_item: ContractNavItem | None
    next_item: ContractNavItem | None
    institutional_rows: list[MemberNetRow]
    retail_rows: list[MemberNetRow]
    institutional_series: list[dict[str, object]]
    institutional_excluding_dongzheng_series: list[dict[str, object]]
    retail_series: list[dict[str, object]]
    switches: list[dict[str, object]]
    weighted_placeholder: str


@dataclass(frozen=True)
class NameCheckResult:
    label: str
    matches: list[str]


class DashboardQueries:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.database = Database(db_path)

    def list_dominant_contracts(self, search: str = "") -> list[ContractIndexItem]:
        items: list[ContractIndexItem] = []
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    exchange,
                    trade_date,
                    lookup_code
                FROM (
                    SELECT DISTINCT
                        exchange,
                        trade_date,
                        CASE WHEN exchange = 'dce' THEN product_name ELSE product_code END AS lookup_code,
                        ROW_NUMBER() OVER (
                            PARTITION BY exchange,
                                CASE WHEN exchange = 'dce' THEN product_name ELSE product_code END
                            ORDER BY trade_date DESC
                        ) AS rn
                    FROM totals
                    WHERE exchange IN ('czce', 'shfe', 'dce')
                )
                WHERE rn = 1
                ORDER BY trade_date DESC, exchange, lookup_code
                """
            ).fetchall()
        for exchange, trade_date, lookup_code in rows:
            if exchange == "czce":
                contract_code = "品种汇总"
            else:
                dominant = get_dominant_contract(self.db_path, exchange, trade_date, lookup_code)
                if dominant is None:
                    continue
                contract_code = dominant.contract_code
            items.append(
                ContractIndexItem(
                    exchange=exchange,
                    product_code=lookup_code,
                    product_name=self._resolve_product_name(exchange, lookup_code),
                    trade_date=trade_date,
                    contract_code=contract_code,
                )
            )
        if not search:
            return items
        normalized_search = search.strip().lower()
        return [
            item
            for item in items
            if normalized_search in item.product_code.lower()
            or normalized_search in item.product_name.lower()
            or normalized_search in item.contract_code.lower()
        ]

    def get_contract_detail(self, exchange: str, product_code: str, trade_date: str) -> ContractDetailData | None:
        dominant = None if exchange == "czce" else get_dominant_contract(self.db_path, exchange, trade_date, product_code)

        available_dates = self._get_available_dates(exchange, product_code)
        previous_item, next_item = self._get_adjacent_items(exchange, product_code, trade_date)
        if exchange == "czce":
            institutional_rows = self._build_member_rows(exchange, trade_date, product_code, "", INSTITUTIONAL_MEMBERS)
            retail_rows = self._build_member_rows(exchange, trade_date, product_code, "", RETAIL_MEMBERS)
            institutional_series = self._build_group_series(exchange, product_code, INSTITUTIONAL_MEMBERS, contract_code="")
            institutional_excluding_dongzheng_series = self._build_group_series(
                exchange,
                product_code,
                INSTITUTIONAL_MEMBERS_EXCLUDING_DONGZHENG,
                contract_code="",
            )
            retail_series = self._build_group_series(exchange, product_code, RETAIL_MEMBERS, contract_code="")
            switch_events: list = []
            contract_code = "品种汇总"
        else:
            if dominant is None:
                return None
            institutional_rows = self._build_member_rows(exchange, trade_date, product_code, dominant.contract_code, INSTITUTIONAL_MEMBERS)
            retail_rows = self._build_member_rows(exchange, trade_date, product_code, dominant.contract_code, RETAIL_MEMBERS)
            institutional_series = self._build_group_series(exchange, product_code, INSTITUTIONAL_MEMBERS)
            institutional_excluding_dongzheng_series = self._build_group_series(
                exchange,
                product_code,
                INSTITUTIONAL_MEMBERS_EXCLUDING_DONGZHENG,
            )
            retail_series = self._build_group_series(exchange, product_code, RETAIL_MEMBERS)
            _, switch_events = get_dominant_switches(self.db_path, exchange, product_code)
            contract_code = dominant.contract_code

        return ContractDetailData(
            exchange=exchange,
            product_code=product_code,
            product_name=self._resolve_product_name(exchange, product_code),
            trade_date=trade_date,
            contract_code=contract_code,
            available_dates=available_dates,
            previous_item=previous_item,
            next_item=next_item,
            institutional_rows=institutional_rows,
            retail_rows=retail_rows,
            institutional_series=institutional_series,
            institutional_excluding_dongzheng_series=institutional_excluding_dongzheng_series,
            retail_series=retail_series,
            switches=[
                {
                    "prev_trade_date": event.prev_trade_date,
                    "trade_date": event.trade_date,
                    "prev_contract_code": event.prev_contract_code,
                    "next_contract_code": event.next_contract_code,
                }
                for event in switch_events
            ],
            weighted_placeholder="加权合约预留，暂未启用",
        )

    def check_member_name_coverage(self) -> list[NameCheckResult]:
        labels = INSTITUTIONAL_MEMBERS + RETAIL_MEMBERS
        with self.database.connect() as connection:
            all_names = {
                row[0] for row in connection.execute("select distinct member_name from rankings where member_name != ''")
            }
        results: list[NameCheckResult] = []
        for label in labels:
            matches = sorted(name for name in all_names if label in name)
            results.append(NameCheckResult(label=label, matches=matches))
        return results

    def _get_available_dates(self, exchange: str, product_code: str) -> list[str]:
        query_field = "product_name" if exchange == "dce" else "product_code"
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT DISTINCT trade_date FROM totals WHERE exchange = ? AND {query_field} = ? ORDER BY trade_date DESC",
                (exchange, product_code),
            ).fetchall()
        return [row[0] for row in rows]

    def _resolve_product_name(self, exchange: str, product_code: str) -> str:
        if exchange == "dce":
            return DCE_PRODUCT_NAMES.get(product_code.upper(), product_code)
        with self.database.connect() as connection:
            row = connection.execute(
                "select product_name from totals where exchange = ? and product_code = ? and product_name != '' limit 1",
                (exchange, product_code),
            ).fetchone()
        return str(row[0]) if row else product_code

    def _get_adjacent_items(
        self,
        exchange: str,
        product_code: str,
        trade_date: str,
    ) -> tuple[ContractNavItem | None, ContractNavItem | None]:
        items = self.list_dominant_contracts()
        for index, item in enumerate(items):
            if item.exchange == exchange and item.product_code == product_code and item.trade_date == trade_date:
                previous_item = items[index - 1] if index > 0 else None
                next_item = items[index + 1] if index + 1 < len(items) else None
                return self._to_nav_item(previous_item), self._to_nav_item(next_item)
        return None, None

    def _to_nav_item(self, item: ContractIndexItem | None) -> ContractNavItem | None:
        if item is None:
            return None
        return ContractNavItem(
            exchange=item.exchange,
            product_code=item.product_code,
            product_name=item.product_name,
            trade_date=item.trade_date,
            contract_code=item.contract_code,
        )

    def _build_group_series(
        self,
        exchange: str,
        product_code: str,
        labels: Iterable[str],
        contract_code: str | None = None,
    ) -> list[dict[str, object]]:
        series: list[dict[str, object]] = []
        available_dates = self._get_available_dates(exchange, product_code)
        for trade_date in reversed(available_dates):
            current_contract_code = contract_code
            if current_contract_code is None:
                dominant = get_dominant_contract(self.db_path, exchange, trade_date, product_code)
                if dominant is None:
                    continue
                current_contract_code = dominant.contract_code
            rows = self._build_member_rows(exchange, trade_date, product_code, current_contract_code, labels)
            series.append(
                {
                    "trade_date": trade_date,
                    "net_position": sum(row.net_position for row in rows),
                }
            )
        return series

    def _build_member_rows(
        self,
        exchange: str,
        trade_date: str,
        product_code: str,
        contract_code: str,
        labels: Iterable[str],
    ) -> list[MemberNetRow]:
        rankings = self._load_contract_rankings(exchange, trade_date, product_code, contract_code)
        rows: list[MemberNetRow] = []
        for label in labels:
            matched_names = sorted(name for name in rankings if label in name)
            long_value = sum(rankings[name].get("long_open_interest", {}).get("value", 0) for name in matched_names)
            short_value = sum(rankings[name].get("short_open_interest", {}).get("value", 0) for name in matched_names)
            long_change = sum(rankings[name].get("long_open_interest", {}).get("change_value", 0) for name in matched_names)
            short_change = sum(rankings[name].get("short_open_interest", {}).get("change_value", 0) for name in matched_names)
            rows.append(
                MemberNetRow(
                    member_label=label,
                    matched_member_names=matched_names,
                    net_position=long_value - short_value,
                    net_change=long_change - short_change,
                    long_value=long_value,
                    short_value=short_value,
                    long_change=long_change,
                    short_change=short_change,
                )
            )
        return rows

    def _load_contract_rankings(
        self,
        exchange: str,
        trade_date: str,
        product_code: str,
        contract_code: str,
    ) -> dict[str, dict[str, dict[str, int]]]:
        result: dict[str, dict[str, dict[str, int]]] = {}
        with self.database.connect() as connection:
            if contract_code:
                rows = connection.execute(
                    """
                    SELECT member_name, ranking_type, value, change_value
                    FROM rankings
                    WHERE exchange = ? AND trade_date = ? AND contract_code = ?
                    """,
                    (exchange, trade_date, contract_code),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT member_name, ranking_type, value, change_value
                    FROM rankings
                    WHERE exchange = ? AND trade_date = ? AND product_code = ?
                    """,
                    (exchange, trade_date, product_code),
                ).fetchall()
        for member_name, ranking_type, value, change_value in rows:
            bucket = result.setdefault(member_name, {})
            bucket[ranking_type] = {
                "value": int(value),
                "change_value": int(change_value),
            }
        return result
