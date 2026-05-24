---
name: futures-seat-tracker
description: 自动下载郑商所日终持仓排名，并解析郑商所/大商所/上期所文件为统一 CSV。
---

这个 skill 用来处理期货交易所日终席位数据。

当前范围：
- 郑商所：支持自动下载与解析
- 大商所：支持手动下载后的 ZIP 解析
- 上期所：支持手动下载后的 TXT 解析

用法示例：
- `python futures_seat_tracker/main.py poll --exchange czce`
- `python futures_seat_tracker/main.py backfill --exchange czce --date 20260518`
- `python futures_seat_tracker/main.py parse --exchange dce --file "D:/Download/日成交持仓排名.zip" --date 20260522`
- `python futures_seat_tracker/main.py parse --exchange shfe --file "D:/Download/日交易排名.txt" --date 20260522`
