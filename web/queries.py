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

PRODUCT_NAME_OVERRIDES = {
    "NR": "20号胶",
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

PRICE_VOLUME_OI_RULES = {
    ("上涨", "增加", "增加"): ("增量上涨", "新资金推动，多头趋势偏强。"),
    ("上涨", "增加", "减少"): ("放量减仓上涨", "上涨更多来自空头回补或短线挤仓，走势强但波动也会放大。"),
    ("上涨", "减少", "增加"): ("缩量增仓上涨", "上涨中持仓继续累积，但跟风成交不足，说明分歧在加大。"),
    ("上涨", "减少", "减少"): ("缩量减仓上涨", "上涨更像修复或被动上行，持续性要继续观察。"),
    ("下跌", "增加", "增加"): ("增量下跌", "新资金推动下跌，空头趋势偏强。"),
    ("下跌", "增加", "减少"): ("放量减仓下跌", "下跌更多来自多头止损或情绪宣泄，短期容易剧烈波动。"),
    ("下跌", "减少", "增加"): ("缩量增仓下跌", "下跌过程中空头仓位继续累积，说明空方在持续施压。"),
    ("下跌", "减少", "减少"): ("缩量减仓下跌", "下跌更像存量资金撤退，走势可能逐步钝化。"),
}


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
class ConditionSignal:
    title: str
    summary: str
    details: list[str]


@dataclass(frozen=True)
class HomeCapitalAlert:
    exchange: str
    product_code: str
    product_name: str
    trade_date: str
    contract_code: str
    market_signal: ConditionSignal
    behavior_signal: ConditionSignal
    composite_signal: ConditionSignal


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
    market_signal: ConditionSignal
    behavior_signal: ConditionSignal
    composite_signal: ConditionSignal
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
            institutional_total = sum(row.net_position for row in institutional_rows)
            institutional_excluding_dongzheng_total = sum(
                row.net_position
                for row in self._build_member_rows(
                    exchange,
                    trade_date,
                    product_code,
                    "",
                    INSTITUTIONAL_MEMBERS_EXCLUDING_DONGZHENG,
                )
            )
            retail_total = sum(row.net_position for row in retail_rows)
            institutional_series = self._build_group_series(
                exchange,
                product_code,
                INSTITUTIONAL_MEMBERS,
                trade_date,
                institutional_total,
                contract_code="",
            )
            institutional_excluding_dongzheng_series = self._build_group_series(
                exchange,
                product_code,
                INSTITUTIONAL_MEMBERS_EXCLUDING_DONGZHENG,
                trade_date,
                institutional_excluding_dongzheng_total,
                contract_code="",
            )
            retail_series = self._build_group_series(
                exchange,
                product_code,
                RETAIL_MEMBERS,
                trade_date,
                retail_total,
                contract_code="",
            )
            switch_events: list = []
            contract_code = dominant.contract_code if dominant is not None else "品种汇总"
        else:
            if dominant is None:
                return None
            institutional_rows = self._build_member_rows(exchange, trade_date, product_code, dominant.contract_code, INSTITUTIONAL_MEMBERS)
            retail_rows = self._build_member_rows(exchange, trade_date, product_code, dominant.contract_code, RETAIL_MEMBERS)
            institutional_total = sum(row.net_position for row in institutional_rows)
            institutional_excluding_dongzheng_total = sum(
                row.net_position
                for row in self._build_member_rows(
                    exchange,
                    trade_date,
                    product_code,
                    dominant.contract_code,
                    INSTITUTIONAL_MEMBERS_EXCLUDING_DONGZHENG,
                )
            )
            retail_total = sum(row.net_position for row in retail_rows)
            institutional_series = self._build_group_series(
                exchange,
                product_code,
                INSTITUTIONAL_MEMBERS,
                trade_date,
                institutional_total,
                contract_code=dominant.contract_code,
            )
            institutional_excluding_dongzheng_series = self._build_group_series(
                exchange,
                product_code,
                INSTITUTIONAL_MEMBERS_EXCLUDING_DONGZHENG,
                trade_date,
                institutional_excluding_dongzheng_total,
                contract_code=dominant.contract_code,
            )
            retail_series = self._build_group_series(
                exchange,
                product_code,
                RETAIL_MEMBERS,
                trade_date,
                retail_total,
                contract_code=dominant.contract_code,
            )
            _, switch_events = get_dominant_switches(self.db_path, exchange, product_code)
            contract_code = dominant.contract_code

        market_signal = self._build_market_structure_signal(exchange, product_code, trade_date, contract_code)
        behavior_signal = self._build_behavior_signal(institutional_rows, retail_rows, market_signal)
        composite_signal = self._build_composite_signal(market_signal, behavior_signal)

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
            market_signal=market_signal,
            behavior_signal=behavior_signal,
            composite_signal=composite_signal,
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
            market_signal = self._build_market_structure_signal(item.exchange, item.product_code, item.trade_date, item.contract_code)
            behavior_signal = self._build_behavior_signal(inst_rows, ret_rows, market_signal)
            composite_signal = self._build_composite_signal(market_signal, behavior_signal)
            alerts.append(
                HomeCapitalAlert(
                    exchange=item.exchange,
                    product_code=item.product_code,
                    product_name=item.product_name,
                    trade_date=item.trade_date,
                    contract_code=item.contract_code,
                    market_signal=market_signal,
                    behavior_signal=behavior_signal,
                    composite_signal=composite_signal,
                )
            )
        alerts.sort(key=lambda a: (0 if a.composite_signal.summary != "结构混合，暂不下明确方向结论。" else 1, a.product_name))
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
        normalized_code = product_code.upper()
        if exchange == "dce":
            return DCE_PRODUCT_NAMES.get(normalized_code, product_code)
        if normalized_code in PRODUCT_NAME_OVERRIDES:
            return PRODUCT_NAME_OVERRIDES[normalized_code]
        with self.database.connect() as connection:
            row = connection.execute(
                "select product_name from totals where exchange = ? and product_code = ? and product_name != '' limit 1",
                (exchange, product_code),
            ).fetchone()
        return str(row[0]) if row else product_code

    def _get_daily_market_summary(
        self, exchange: str, trade_date: str, contract_code: str
    ) -> tuple[float | None, float | None, float | None, float | None, int | None, int | None]:
        snapshot = self._get_daily_market_snapshot(exchange, trade_date, contract_code)
        if not snapshot:
            return None, None, None, None, None, None
        return (
            snapshot["close_price"],
            snapshot["settlement_price"],
            snapshot["close_change"],
            snapshot["settlement_change"],
            snapshot["volume"],
            snapshot["open_interest"],
        )

    def _get_daily_market_snapshot(self, exchange: str, trade_date: str, contract_code: str) -> dict[str, object] | None:
        if not contract_code or contract_code == "品种汇总":
            return None
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT close_price, settlement_price, close_change, settlement_change, volume, open_interest, open_interest_change
                FROM daily_markets
                WHERE trade_date = ? AND exchange = ? AND contract_code = ?
                """,
                (trade_date, exchange, contract_code),
            ).fetchone()
        if not row:
            return None
        return {
            "close_price": row[0],
            "settlement_price": row[1],
            "close_change": row[2],
            "settlement_change": row[3],
            "volume": int(row[4]) if row[4] is not None else None,
            "open_interest": int(row[5]) if row[5] is not None else None,
            "open_interest_change": int(row[6]) if row[6] is not None else None,
        }

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
        anchor_trade_date: str,
        anchor_net_position: int,
        contract_code: str | None = None,
    ) -> list[dict[str, object]]:
        available_dates = list(reversed(self._get_available_dates(exchange, product_code)))
        if anchor_trade_date not in available_dates:
            return []

        daily_changes: dict[str, int] = {}
        for trade_date in available_dates:
            current_contract_code = contract_code
            if current_contract_code is None:
                dominant = get_dominant_contract(self.db_path, exchange, trade_date, product_code)
                if dominant is None:
                    continue
                current_contract_code = dominant.contract_code
            rows = self._build_member_rows(exchange, trade_date, product_code, current_contract_code, labels)
            daily_changes[trade_date] = sum(row.net_change for row in rows)

        anchor_index = available_dates.index(anchor_trade_date)
        net_positions = [0] * len(available_dates)
        net_positions[anchor_index] = anchor_net_position

        for index in range(anchor_index + 1, len(available_dates)):
            net_positions[index] = net_positions[index - 1] + daily_changes.get(available_dates[index], 0)
        for index in range(anchor_index - 1, -1, -1):
            next_trade_date = available_dates[index + 1]
            net_positions[index] = net_positions[index + 1] - daily_changes.get(next_trade_date, 0)

        return [
            {
                "trade_date": trade_date,
                "net_position": net_positions[index],
            }
            for index, trade_date in enumerate(available_dates)
        ]

    def _build_market_structure_signal(
        self,
        exchange: str,
        product_code: str,
        trade_date: str,
        contract_code: str,
    ) -> ConditionSignal:
        current = self._get_daily_market_snapshot(exchange, trade_date, contract_code)
        previous_date = self._get_previous_trade_date(exchange, product_code, trade_date)
        previous = self._get_daily_market_snapshot(exchange, previous_date, contract_code) if previous_date else None
        if not current or not previous:
            return ConditionSignal(
                title="量价关系判断",
                summary="条件不足，暂时无法完成量价关系归类。",
                details=["当前合约缺少完整的当日或上一交易日日行情数据。"],
            )

        price_direction = self._price_direction(current)
        volume_direction = self._compare_direction(current.get("volume"), previous.get("volume"))
        oi_direction = self._open_interest_direction(current, previous)
        combo = PRICE_VOLUME_OI_RULES.get((price_direction, volume_direction, oi_direction))
        if not combo:
            return ConditionSignal(
                title="量价关系判断",
                summary="条件不足或方向不明确，暂不强行归入固定量价组合。",
                details=[
                    f"价格：{price_direction}",
                    f"成交量：{volume_direction}",
                    f"持仓量：{oi_direction}",
                ],
            )
        label, meaning = combo
        return ConditionSignal(
            title="量价关系判断",
            summary=f"{label}：{meaning}",
            details=[
                f"价格：{price_direction}",
                f"成交量：{volume_direction}",
                f"持仓量：{oi_direction}",
                f"组合：{label}",
                f"含义：{meaning}",
            ],
        )

    def _build_behavior_signal(
        self,
        institutional_rows: list[MemberNetRow],
        retail_rows: list[MemberNetRow],
        market_signal: ConditionSignal,
    ) -> ConditionSignal:
        inst = self._group_profile(institutional_rows, "机构")
        retail = self._group_profile(retail_rows, "散户")
        oi_contracting = "持仓量：减少" in market_signal.details
        details = [
            f"机构立场：{inst['stance_label']}",
            f"机构行为：{inst['action_label']}",
            f"散户立场：{retail['stance_label']}",
            f"散户行为：{retail['action_label']}",
        ]

        if inst["stance"] == "net_long" and retail["stance"] == "net_short":
            if retail["action"] in {"reduce_short", "increase_long", "both_reduce"} and oi_contracting:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary="散户空头开始止损回补，对手盘燃料在衰减，需警惕上涨进入后段。",
                    details=details + ["解释：原有机构多、散户空的结构开始松动，持仓同步收缩。"],
                )
            if inst["action"] in {"increase_long", "reduce_short", "both_add"} and retail["action"] in {"increase_short", "reduce_long", "both_add", "both_reduce"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary="机构主导做多，散户继续逆势做空，对手盘结构仍在，趋势延续。",
                    details=details + ["解释：机构仍站在多头主导一侧，散户继续提供空头对手盘。"],
                )
            if inst["action"] in {"reduce_long", "increase_short", "both_reduce"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary="机构仍偏多，但主动推进在放缓。",
                    details=details + ["解释：机构净多未改，但当日没有继续强化多头。"],
                )
            return ConditionSignal(
                title="机构/散户行为判断",
                summary="机构仍主导多头，散户仍站在空头对手盘，趋势暂未破坏。",
                details=details + ["解释：虽然当日动作不完全标准，但主导方向仍是机构多、散户空。"],
            )

        if inst["stance"] == "net_short" and retail["stance"] == "net_long":
            if retail["action"] in {"reduce_long", "increase_short", "both_reduce"} and oi_contracting:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary="散户多头开始止损离场，对手盘燃料在衰减，需警惕下跌进入后段。",
                    details=details + ["解释：原有机构空、散户多的结构开始松动，持仓同步收缩。"],
                )
            if inst["action"] in {"increase_short", "reduce_long", "both_add"} and retail["action"] in {"increase_long", "reduce_short", "both_add", "both_reduce"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary="机构主导做空，散户逆势承接多头，对手盘结构仍在，跌势延续。",
                    details=details + ["解释：机构仍站在空头主导一侧，散户继续提供多头对手盘。"],
                )
            if inst["action"] in {"reduce_short", "increase_long", "both_reduce"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary="机构仍偏空，但主动推进在放缓。",
                    details=details + ["解释：机构净空未改，但当日没有继续强化空头。"],
                )
            return ConditionSignal(
                title="机构/散户行为判断",
                summary="机构仍主导空头，散户仍站在多头对手盘，趋势暂未破坏。",
                details=details + ["解释：虽然当日动作不完全标准，但主导方向仍是机构空、散户多。"],
            )

        if inst["stance"] == retail["stance"] and inst["stance"] != "neutral":
            direction = "做多" if inst["stance"] == "net_long" else "做空"
            if inst["action"] in {"increase_long", "increase_short", "both_add"} and retail["action"] in {"increase_long", "increase_short", "both_add"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary=f"机构与散户同向{direction}并同步加仓，属于一致性强趋势或事件驱动结构。",
                    details=details + ["解释：这不是常规的机构吃散户，而是顺向资金共振。"],
                )
            if inst["action"] in {"reduce_long", "reduce_short", "both_reduce"} and retail["action"] in {"reduce_long", "reduce_short", "both_reduce"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary="机构与散户同向但都在减仓，原趋势可能进入钝化或整理阶段。",
                    details=details + ["解释：顺向持仓还在，但双方都没有继续强化原方向。"],
                )
            if inst["action"] in {"increase_long", "increase_short", "both_add"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary=f"机构仍主导{direction}，但散户没有同步强化，当前更像机构单边推动。",
                    details=details + ["解释：方向仍由机构主导，只是散户没有形成同步共振。"],
                )
            if inst["action"] in {"reduce_long", "reduce_short", "both_reduce"}:
                return ConditionSignal(
                    title="机构/散户行为判断",
                    summary=f"机构与散户同向{direction}，但机构也在收缩仓位，趋势推进开始放缓。",
                    details=details + ["解释：虽然方向一致，但主导资金没有继续强化原方向。"],
                )

        if inst["stance"] == "net_long" and inst["action"] in {"reduce_long", "increase_short", "both_reduce"}:
            return ConditionSignal(
                title="机构/散户行为判断",
                summary="机构仍偏多，但推进力度在减弱。",
                details=details + ["解释：机构主导方向未变，但当日行为开始反着多头主导方向走。"],
            )
        if inst["stance"] == "net_short" and inst["action"] in {"reduce_short", "increase_long", "both_reduce"}:
            return ConditionSignal(
                title="机构/散户行为判断",
                summary="机构仍偏空，但推进力度在减弱。",
                details=details + ["解释：机构主导方向未变，但当日行为开始反着空头主导方向走。"],
            )
        return ConditionSignal(
            title="机构/散户行为判断",
            summary="机构与散户结构混合，暂不下明确方向结论。",
            details=details + ["解释：当前席位结构没有落入清晰的主导延续、顺向共振或燃料衰减场景。"],
        )

    def _build_composite_signal(
        self,
        market_signal: ConditionSignal,
        behavior_signal: ConditionSignal,
    ) -> ConditionSignal:
        market_summary = market_signal.summary
        behavior_summary = behavior_signal.summary
        if "趋势延续" in behavior_summary or "跌势延续" in behavior_summary:
            summary = f"{market_summary}{behavior_summary}"
        elif "止损" in behavior_summary or "后段" in behavior_summary:
            summary = f"{market_summary}{behavior_summary}"
        elif "同步加仓" in behavior_summary:
            summary = f"{market_summary}{behavior_summary}"
        elif "推进力度在减弱" in behavior_summary:
            summary = f"{market_summary}{behavior_summary}"
        elif "机构仍主导" in behavior_summary or "机构与散户同向但都在减仓" in behavior_summary:
            summary = f"{market_summary}{behavior_summary}"
        else:
            summary = "结构混合，暂不下明确方向结论。"
        return ConditionSignal(
            title="综合判断",
            summary=summary,
            details=[
                f"量价关系：{market_signal.summary}",
                f"机构/散户：{behavior_signal.summary}",
            ],
        )

    def _get_previous_trade_date(self, exchange: str, product_code: str, trade_date: str) -> str | None:
        available_dates = list(reversed(self._get_available_dates(exchange, product_code)))
        if trade_date not in available_dates:
            return None
        index = available_dates.index(trade_date)
        if index <= 0:
            return None
        return available_dates[index - 1]

    def _price_direction(self, snapshot: dict[str, object]) -> str:
        change = float(snapshot.get("close_change") or 0)
        if change > 0:
            return "上涨"
        if change < 0:
            return "下跌"
        return "不明确"

    def _compare_direction(self, current: object, previous: object) -> str:
        if current is None or previous is None:
            return "不明确"
        if current > previous:
            return "增加"
        if current < previous:
            return "减少"
        return "不明确"

    def _open_interest_direction(self, current: dict[str, object], previous: dict[str, object]) -> str:
        oi_change = current.get("open_interest_change")
        if isinstance(oi_change, int):
            if oi_change > 0:
                return "增加"
            if oi_change < 0:
                return "减少"
        return self._compare_direction(current.get("open_interest"), previous.get("open_interest"))

    def _group_profile(self, rows: list[MemberNetRow], group_name: str) -> dict[str, str]:
        net_position = sum(row.net_position for row in rows)
        long_change = sum(row.long_change for row in rows)
        short_change = sum(row.short_change for row in rows)
        if net_position > 0:
            stance = "net_long"
            stance_label = f"{group_name}净多"
        elif net_position < 0:
            stance = "net_short"
            stance_label = f"{group_name}净空"
        else:
            stance = "neutral"
            stance_label = f"{group_name}中性"

        if long_change > 0 and short_change <= 0:
            action = "increase_long"
            action_label = "增多"
        elif long_change < 0 and short_change >= 0:
            action = "reduce_long"
            action_label = "减多"
        elif short_change > 0 and long_change <= 0:
            action = "increase_short"
            action_label = "增空"
        elif short_change < 0 and long_change >= 0:
            action = "reduce_short"
            action_label = "减空"
        elif long_change > 0 and short_change > 0:
            action = "both_add"
            action_label = "多空同增"
        elif long_change < 0 and short_change < 0:
            action = "both_reduce"
            action_label = "多空同减"
        else:
            action = "mixed"
            action_label = "混合"
        return {
            "stance": stance,
            "stance_label": stance_label,
            "action": action,
            "action_label": action_label,
        }

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
