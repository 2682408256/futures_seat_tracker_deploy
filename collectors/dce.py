from __future__ import annotations

from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

from futures_seat_tracker.config import RAW_DIR
from futures_seat_tracker.models import DownloadResult

ENTRY_URL = "http://www.dce.com.cn/frontend/dcereport/"
BASE_URL = "http://www.dce.com.cn/dcereport/publicweb/dailystat/memberDealPosi/batchDownload"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "http://www.dce.com.cn",
    "Referer": "http://www.dce.com.cn/frontend/dcereport/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "clientId": "web",
}
DEFAULT_PAYLOAD = {
    "varietyId": "bz",
    "contractId": "all",
    "tradeType": "1",
    "lang": "zh",
}


class DceCollector:
    exchange = "dce"

    def build_output_path(self, trade_date: str) -> Path:
        year = trade_date[:4]
        return RAW_DIR / self.exchange / year / trade_date / f"{trade_date}_DPL.zip"

    def fetch_session(self) -> dict[str, str]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            cookies = {cookie["name"]: cookie["value"] for cookie in context.cookies()}
            browser.close()
        return cookies

    def download(self, trade_date: str, cookies: dict[str, str] | None = None, timeout: int = 30) -> DownloadResult:
        session_cookies = cookies or self.fetch_session()
        url = BASE_URL
        target = self.build_output_path(trade_date)
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = dict(DEFAULT_PAYLOAD)
        payload["tradeDate"] = trade_date

        response = requests.post(url, headers=HEADERS, cookies=session_cookies, json=payload, timeout=timeout, allow_redirects=True)
        found = response.status_code == 200 and response.headers.get("Content-Type", "").startswith("application/zip")

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
