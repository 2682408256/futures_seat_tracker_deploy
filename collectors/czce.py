from __future__ import annotations

from datetime import datetime
from pathlib import Path

import requests

from futures_seat_tracker.config import RAW_DIR
from futures_seat_tracker.models import DownloadResult

BASE_URL = "https://www.czce.com.cn/cn/DFSStaticFiles/Future/{year}/{date}/FutureDataHolding.txt"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
    "Accept": "text/plain,*/*",
    "Referer": "https://www.czce.com.cn/",
}


class CzceCollector:
    exchange = "czce"

    def build_url(self, trade_date: str) -> str:
        dt = datetime.strptime(trade_date, "%Y%m%d")
        return BASE_URL.format(year=dt.strftime("%Y"), date=trade_date)

    def build_output_path(self, trade_date: str) -> Path:
        year = trade_date[:4]
        return RAW_DIR / self.exchange / year / trade_date / "FutureDataHolding.txt"

    def download(self, trade_date: str, timeout: int = 30) -> DownloadResult:
        url = self.build_url(trade_date)
        target = self.build_output_path(trade_date)
        target.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(url, headers=HEADERS, timeout=timeout)
        found = response.status_code == 200 and "郑州商品交易所期货持仓排名表" in response.text

        if found:
            target.write_bytes(response.content)
        elif target.exists():
            target.unlink()

        return DownloadResult(
            exchange=self.exchange,
            trade_date=trade_date,
            source_url=url,
            file_path=target,
            found=found,
        )
