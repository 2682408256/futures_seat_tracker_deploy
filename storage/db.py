from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS instruments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_date TEXT NOT NULL,
        exchange TEXT NOT NULL,
        product_code TEXT NOT NULL,
        product_name TEXT NOT NULL,
        raw_title TEXT NOT NULL,
        contract_code TEXT NOT NULL DEFAULT '',
        source_file TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(trade_date, exchange, product_code, contract_code, raw_title)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rankings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_date TEXT NOT NULL,
        exchange TEXT NOT NULL,
        product_code TEXT NOT NULL,
        product_name TEXT NOT NULL,
        contract_code TEXT NOT NULL DEFAULT '',
        ranking_type TEXT NOT NULL,
        rank INTEGER NOT NULL,
        member_name TEXT NOT NULL,
        value INTEGER NOT NULL,
        change_value INTEGER NOT NULL,
        source_file TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(trade_date, exchange, product_code, contract_code, ranking_type, rank, member_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS totals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_date TEXT NOT NULL,
        exchange TEXT NOT NULL,
        product_code TEXT NOT NULL,
        product_name TEXT NOT NULL,
        contract_code TEXT NOT NULL DEFAULT '',
        ranking_type TEXT NOT NULL,
        total_value INTEGER NOT NULL,
        total_change_value INTEGER NOT NULL,
        source_file TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(trade_date, exchange, product_code, contract_code, ranking_type)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_markets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trade_date TEXT NOT NULL,
        exchange TEXT NOT NULL,
        product_code TEXT NOT NULL,
        product_name TEXT NOT NULL,
        contract_code TEXT NOT NULL,
        open_price REAL NOT NULL DEFAULT 0,
        high_price REAL NOT NULL DEFAULT 0,
        low_price REAL NOT NULL DEFAULT 0,
        close_price REAL NOT NULL DEFAULT 0,
        settlement_price REAL NOT NULL DEFAULT 0,
        previous_settlement_price REAL NOT NULL DEFAULT 0,
        change_value REAL NOT NULL DEFAULT 0,
        close_change REAL NOT NULL DEFAULT 0,
        settlement_change REAL NOT NULL DEFAULT 0,
        change_pct REAL NOT NULL DEFAULT 0,
        volume INTEGER NOT NULL DEFAULT 0,
        open_interest INTEGER NOT NULL DEFAULT 0,
        open_interest_change INTEGER NOT NULL DEFAULT 0,
        turnover REAL NOT NULL DEFAULT 0,
        source_file TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(trade_date, exchange, product_code, contract_code)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_instruments_trade_exchange_product ON instruments(trade_date, exchange, product_code)",
    "CREATE INDEX IF NOT EXISTS idx_rankings_trade_exchange_product_contract_type ON rankings(trade_date, exchange, product_code, contract_code, ranking_type)",
    "CREATE INDEX IF NOT EXISTS idx_rankings_member_trade ON rankings(member_name, trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_totals_trade_exchange_product_contract_type ON totals(trade_date, exchange, product_code, contract_code, ranking_type)",
    "CREATE INDEX IF NOT EXISTS idx_daily_markets_trade_exchange ON daily_markets(trade_date, exchange)",
    "CREATE INDEX IF NOT EXISTS idx_daily_markets_exchange_product_contract ON daily_markets(exchange, product_code, contract_code)",
]


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._ensure_daily_market_columns(connection)
            connection.commit()

    def _ensure_daily_market_columns(self, connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(daily_markets)")}
        migrations = {
            "open_interest_change": "ALTER TABLE daily_markets ADD COLUMN open_interest_change INTEGER NOT NULL DEFAULT 0",
            "turnover": "ALTER TABLE daily_markets ADD COLUMN turnover REAL NOT NULL DEFAULT 0",
            "close_change": "ALTER TABLE daily_markets ADD COLUMN close_change REAL NOT NULL DEFAULT 0",
            "settlement_change": "ALTER TABLE daily_markets ADD COLUMN settlement_change REAL NOT NULL DEFAULT 0",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)
