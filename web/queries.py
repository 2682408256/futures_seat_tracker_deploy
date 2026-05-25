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
    "摩根大通",
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
    close_price: float | None
    settlement_price: float | None
    close_change: float | None
    settlement_change: float | None
    volume: int | None
    open_interest: int | None


@dataclass(frozen=True)
class ContractNavItem:
    exchange: str
    product_code: str
    product_name: str
    trade_date: str
    contract_code: str


@dataclass(frozen=True)
class HomeCapitalAlert:
    exchange: str
    product_code: str
    product_name: str
    trade_date: str
    contract_code: str
    level: str
    message: str
    score: int


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
    capital_alerts: list[str]
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

    def list_dominant_contracts(self, search: str = "", trade_date: str = "") -> list[ContractIndexItem]:
        items: list[ContractIndexItem] = []
        normalized_trade_date = self._normalize_trade_date(trade_date)
        with self.database.connect() as connection:
            if normalized_trade_date:
                rows = connection.execute(
                    """
                    SELECT DISTINCT
                        exchange,
                        trade_date,
                        CASE WHEN exchange = 'dce' THEN product_name ELSE product_code END AS lookup_code
                    FROM totals
                    WHERE exchange IN ('czce', 'shfe', 'dce')
                      AND trade_date = ?
                    ORDER BY exchange, lookup_code
                    """,
                    (normalized_trade_date,),
                ).fetchall()
            else:
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
            dominant = get_dominant_contract(self.db_path, exchange, trade_date, lookup_code)
            if dominant is None:
                contract_code = "品种汇总" if exchange == "czce" else ""
            else:
                contract_code = dominant.contract_code
            if not contract_code:
                continue
            daily_market = self._get_daily_market_summary(exchange, trade_date, contract_code)
            items.append(
                ContractIndexItem(
                    exchange=exchange,
                    product_code=lookup_code,
                    product_name=self._resolve_product_name(exchange, lookup_code),
                    trade_date=trade_date,
                    contract_code=contract_code,
                    close_price=daily_market[0],
                    settlement_price=daily_market[1],
                    close_change=daily_market[2],
                    settlement_change=daily_market[3],
                    volume=daily_market[4],
                    open_interest=daily_market[5],
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
        dominant = get_dominant_contract(self.db_path, exchange, trade_date, product_code)

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
            contract_code = dominant.contract_code if dominant is not None else "品种汇总"
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

        capital_alerts = self._build_capital_alerts(
            exchange,
            product_code,
            trade_date,
            contract_code,
            institutional_rows,
            retail_rows,
            institutional_series,
            retail_series,
        )

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
            capital_alerts=capital_alerts,
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

    def list_trade_dates(self) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT trade_date
                FROM totals
                WHERE exchange IN ('czce', 'shfe', 'dce')
                ORDER BY trade_date DESC
                """
            ).fetchall()
        return [str(row[0]) for row in rows]

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

    def get_home_capital_alerts(self, limit: int = 10) -> list[HomeCapitalAlert]:
        items = self.list_dominant_contracts()
        alerts: list[HomeCapitalAlert] = []
        for item in items:
            contract_code = "" if item.exchange == "czce" else item.contract_code
            inst_rows = self._build_member_rows(item.exchange, item.trade_date, item.product_code, contract_code, INSTITUTIONAL_MEMBERS)
            ret_rows = self._build_member_rows(item.exchange, item.trade_date, item.product_code, contract_code, RETAIL_MEMBERS)
            inst_change = sum(row.net_change for row in inst_rows)
            ret_change = sum(row.net_change for row in ret_rows)
            active_inst = [row for row in inst_rows if row.net_change != 0]
            pos = sum(1 for row in active_inst if row.net_change > 0)
            neg = sum(1 for row in active_inst if row.net_change < 0)
            total = len(active_inst)
            score = abs(inst_change)
            level = "异动"
            parts: list[str] = []
            if inst_change:
                direction = "增加" if inst_change > 0 else "减少"
                parts.append(f"机构净持仓{direction} {abs(inst_change):,} 手")
            if inst_change * ret_change < 0:
                inst_dir = "增多" if inst_change > 0 else "减多"
                ret_dir = "增多" if ret_change > 0 else "减多"
                level = "分歧"
                score += abs(ret_change)
                parts.append(f"机构{inst_dir}、散户{ret_dir}")
            if total >= 3:
                if max(pos, neg) / total >= 0.7:
                    direction = "增多" if pos > neg else "减多"
                    level = "主力统一" if level == "异动" else level
                    score += 20000
                    parts.append(f"{max(pos, neg)}/{total} 个机构席位同步{direction}")
                elif pos >= 2 and neg >= 2:
                    level = "主力分歧" if level == "异动" else level
                    score += 20000
                    parts.append(f"{pos} 个席位增多、{neg} 个席位减多")
            if abs(inst_change) >= 10000:
                level = "强异动" if level == "异动" else level
                score += 30000
            if parts and score >= 5000:
                alerts.append(
                    HomeCapitalAlert(
                        exchange=item.exchange,
                        product_code=item.product_code,
                        product_name=item.product_name,
                        trade_date=item.trade_date,
                        contract_code=item.contract_code,
                        level=level,
                        message="；".join(parts),
                        score=score,
                    )
                )
        alerts.sort(key=lambda a: (-a.score, a.product_name))
        return alerts[:limit]

    def _normalize_trade_date(self, value: str) -> str:
        value = value.strip()
        if len(value) == 8 and value.isdigit():
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
        return value

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

    def _get_daily_market_summary(
        self, exchange: str, trade_date: str, contract_code: str
    ) -> tuple[float | None, float | None, float | None, float | None, int | None, int | None]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT close_price, settlement_price, close_change, settlement_change, volume, open_interest
                FROM daily_markets
                WHERE trade_date = ? AND exchange = ? AND contract_code = ?
                """,
                (trade_date, exchange, contract_code),
            ).fetchone()
        if not row:
            return None, None, None, None, None, None
        return row[0], row[1], row[2], row[3], row[4], row[5]

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

    def _build_capital_alerts(
        self,
        exchange: str,
        product_code: str,
        trade_date: str,
        contract_code: str,
        institutional_rows: list[MemberNetRow],
        retail_rows: list[MemberNetRow],
        institutional_series: list[dict[str, object]],
        retail_series: list[dict[str, object]],
    ) -> list[str]:
        alerts: list[str] = []
        inst_current, inst_previous, inst_avg = self._series_change_stats(institutional_series, trade_date)
        retail_current, retail_previous, retail_avg = self._series_change_stats(retail_series, trade_date)
        if inst_current is not None and inst_previous is not None:
            inst_change = inst_current - inst_previous
            if inst_avg > 0 and abs(inst_change) >= inst_avg * 2:
                direction = "增加" if inst_change > 0 else "减少"
                alerts.append(
                    f"机构阵营净持仓较上一交易日{direction} {abs(inst_change):,} 手，约为近20日平均变化的 {abs(inst_change) / inst_avg:.1f} 倍。"
                )
            elif inst_previous and abs(inst_change / inst_previous) >= 0.2:
                direction = "增加" if inst_change > 0 else "减少"
                alerts.append(f"机构阵营净持仓较上一交易日{direction} {abs(inst_change):,} 手，变化幅度超过 20%。")
        if inst_current is not None and inst_previous is not None and retail_current is not None and retail_previous is not None:
            inst_change = inst_current - inst_previous
            retail_change = retail_current - retail_previous
            if inst_change * retail_change < 0:
                inst_direction = "增多" if inst_change > 0 else "减多"
                retail_direction = "增多" if retail_change > 0 else "减多"
                alerts.append(f"机构阵营{inst_direction}、散户阵营{retail_direction}，阵营方向出现背离。")
        member_alert = self._build_member_change_alert(exchange, product_code, trade_date, contract_code, institutional_rows)
        if member_alert:
            alerts.append(member_alert)
        consensus_alert = self._build_consensus_alert(institutional_rows)
        if consensus_alert:
            alerts.append(consensus_alert)
        if not alerts:
            alerts.append("暂无明显资金异动，机构席位变化整体处于正常范围。")
        return alerts

    def _series_change_stats(self, series: list[dict[str, object]], trade_date: str) -> tuple[int | None, int | None, float]:
        index = next((i for i, item in enumerate(series) if item["trade_date"] == trade_date), -1)
        if index <= 0:
            return None, None, 0.0
        current = int(series[index]["net_position"])
        previous = int(series[index - 1]["net_position"])
        changes = [
            abs(int(series[i]["net_position"]) - int(series[i - 1]["net_position"]))
            for i in range(max(1, index - 19), index + 1)
        ]
        average = sum(changes) / len(changes) if changes else 0.0
        return current, previous, average

    def _build_member_change_alert(
        self,
        exchange: str,
        product_code: str,
        trade_date: str,
        contract_code: str,
        institutional_rows: list[MemberNetRow],
    ) -> str:
        available_dates = list(reversed(self._get_available_dates(exchange, product_code)))
        current_index = available_dates.index(trade_date) if trade_date in available_dates else -1
        if current_index <= 0:
            return ""
        strongest_row = max(institutional_rows, key=lambda row: abs(row.net_change), default=None)
        if strongest_row is None or strongest_row.net_change == 0:
            return ""
        history: list[int] = []
        for date in available_dates[max(0, current_index - 20):current_index]:
            current_contract_code = contract_code
            if exchange != "czce":
                dominant = get_dominant_contract(self.db_path, exchange, date, product_code)
                if dominant is None:
                    continue
                current_contract_code = dominant.contract_code
            rows = self._build_member_rows(exchange, date, product_code, current_contract_code if exchange != "czce" else "", [strongest_row.member_label])
            if rows:
                history.append(abs(rows[0].net_change))
        average = sum(history) / len(history) if history else 0.0
        if average > 0 and abs(strongest_row.net_change) >= average * 2:
            direction = "增加" if strongest_row.net_change > 0 else "减少"
            return f"{strongest_row.member_label} 净持仓{direction} {abs(strongest_row.net_change):,} 手，约为近20日平均变化的 {abs(strongest_row.net_change) / average:.1f} 倍。"
        return ""

    def _build_consensus_alert(self, institutional_rows: list[MemberNetRow]) -> str:
        active_rows = [row for row in institutional_rows if row.net_change != 0]
        if len(active_rows) < 3:
            return ""
        positive_count = sum(1 for row in active_rows if row.net_change > 0)
        negative_count = sum(1 for row in active_rows if row.net_change < 0)
        total = len(active_rows)
        if max(positive_count, negative_count) / total >= 0.7:
            direction = "增多" if positive_count > negative_count else "减多"
            return f"主力意见较统一：{max(positive_count, negative_count)}/{total} 个机构席位同步{direction}。"
        if positive_count >= 2 and negative_count >= 2:
            return f"主力产生分歧：{positive_count} 个机构席位增多，{negative_count} 个机构席位减多。"
        return ""

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
