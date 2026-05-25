from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests

from futures_seat_tracker.config import RAW_DIR
from futures_seat_tracker.models import DownloadResult

HOLDING_URL = "https://www.czce.com.cn/cn/DFSStaticFiles/Future/{year}/{date}/FutureDataHolding.txt"
DAILY_URL = "https://www.czce.com.cn/cn/DFSStaticFiles/Future/{year}/{date}/FutureDataDaily.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
    "Accept": "text/plain,*/*",
    "Referer": "https://www.czce.com.cn/",
}


class CzceCollector:
    exchange = "czce"

    def build_url(self, trade_date: str) -> str:
        dt = datetime.strptime(trade_date, "%Y%m%d")
        return HOLDING_URL.format(year=dt.strftime("%Y"), date=trade_date)

    def build_daily_url(self, trade_date: str) -> str:
        dt = datetime.strptime(trade_date, "%Y%m%d")
        return DAILY_URL.format(year=dt.strftime("%Y"), date=trade_date)

    def build_output_path(self, trade_date: str) -> Path:
        return self._build_output_path(trade_date, "FutureDataHolding.txt")

    def build_daily_output_path(self, trade_date: str) -> Path:
        return self._build_output_path(trade_date, "FutureDataDaily.txt")

    def download(self, trade_date: str, timeout: int = 30) -> DownloadResult:
        url = self.build_url(trade_date)
        target = self.build_output_path(trade_date)
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        found = response.status_code == 200 and "郑州商品交易所期货持仓排名表" in response.text
        return self._save_result(trade_date, url, target, response.content, found)

    def download_daily(self, trade_date: str, timeout: int = 30) -> DownloadResult:
        url = self.build_daily_url(trade_date)
        target = self.build_daily_output_path(trade_date)
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        content_type = response.headers.get("Content-Type", "").lower()
        text = response.text.strip() if response.status_code == 200 else ""
        found = response.status_code == 200 and bool(text) and "text/html" not in content_type and "<html" not in text[:200].lower()
        return self._save_result(trade_date, url, target, response.content, found)

    def _build_output_path(self, trade_date: str, file_name: str) -> Path:
        year = trade_date[:4]
        return RAW_DIR / self.exchange / year / trade_date / file_name

    def _save_result(self, trade_date: str, url: str, target: Path, content: bytes, found: bool) -> DownloadResult:
        target.parent.mkdir(parents=True, exist_ok=True)
        if found:
            target.write_bytes(content)
        elif target.exists():
            target.unlink()
        return DownloadResult(
            exchange=self.exchange,
            trade_date=trade_date,
            source_url=url,
            file_path=target,
            found=found,
        )
