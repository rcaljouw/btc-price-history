#!/usr/bin/env python3
"""Append missing daily BTC/USD candles from the Bitstamp public API to the CSV.

- Reads the last date in data/btc-usd-daily.csv (or starts at the beginning
  of Bitstamp's history when the file only has a header).
- Fetches only completed UTC days (today's still-open candle is skipped).
- Deduplicates, sorts and reports any gaps.
Standard library only, so the workflow needs no pip install.
"""
import csv
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "btc-usd-daily.csv"
FIELDS = ["date", "open", "high", "low", "close", "volume", "source"]
SOURCE = "bitstamp"
API = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
FIRST_DAY = datetime(2011, 8, 1, tzinfo=timezone.utc)  # Bitstamp history starts Aug 2011
DAY = 86400
PAGE = 1000  # Bitstamp maximum per request


def fetch(start_ts: int) -> list[dict]:
    url = f"{API}?step={DAY}&limit={PAGE}&start={start_ts}"
    req = urllib.request.Request(url, headers={"User-Agent": "btc-price-history/1.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)["data"]["ohlc"]
        except Exception as exc:  # network hiccup or rate limit
            wait = 2 ** attempt * 5
            print(f"fetch failed ({exc}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("Bitstamp API unreachable after 5 attempts")


def to_row(candle: dict) -> dict:
    day = datetime.fromtimestamp(int(candle["timestamp"]), tz=timezone.utc).date()
    return {
        "date": day.isoformat(),
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
        "volume": candle["volume"],
        "source": SOURCE,
    }


def load() -> dict[str, dict]:
    if not CSV_PATH.exists():
        return {}
    with CSV_PATH.open(newline="") as f:
        return {r["date"]: r for r in csv.DictReader(f)}


def save(rows: dict[str, dict]) -> None:
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for d in sorted(rows):
            writer.writerow(rows[d])


def report_gaps(rows: dict[str, dict]) -> None:
    dates = sorted(datetime.fromisoformat(d).date() for d in rows)
    gaps = [(a, b) for a, b in zip(dates, dates[1:]) if (b - a).days > 1]
    for a, b in gaps[:20]:
        print(f"gap: no data between {a} and {b}")
    if len(gaps) > 20:
        print(f"... and {len(gaps) - 20} more gaps")


def main() -> None:
    rows = load()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if rows:
        start = datetime.fromisoformat(max(rows)).replace(tzinfo=timezone.utc) + timedelta(days=1)
    else:
        start = FIRST_DAY
    start_ts, end_ts = int(start.timestamp()), int(today.timestamp())

    added = 0
    while start_ts < end_ts:
        candles = [c for c in fetch(start_ts) if start_ts <= int(c["timestamp"]) < end_ts]
        if not candles:
            break
        for c in candles:
            row = to_row(c)
            if row["date"] not in rows:
                added += 1
            rows[row["date"]] = row
        start_ts = max(int(c["timestamp"]) for c in candles) + DAY
        time.sleep(1)  # be polite to the API

    save(rows)
    report_gaps(rows)
    last = max(rows) if rows else "none"
    print(f"added {added} day(s); {len(rows)} total; last date {last}")


if __name__ == "__main__":
    main()
