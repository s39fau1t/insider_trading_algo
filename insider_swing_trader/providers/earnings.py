from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Protocol

from insider_swing_trader.models import EarningsEvent, EarningsTiming


class EarningsProvider(Protocol):
    def events(self, start: date, end: date) -> Iterable[EarningsEvent]:
        ...


class CsvEarningsProvider:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path

    def events(self, start: date, end: date) -> Iterable[EarningsEvent]:
        with self.csv_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                earnings_date = date.fromisoformat(row["earnings_date"])
                if not start <= earnings_date <= end:
                    continue
                yield EarningsEvent(
                    ticker=row["ticker"].strip().upper(),
                    earnings_date=earnings_date,
                    timing=EarningsTiming(row.get("timing", "UNKNOWN").strip().upper()),
                    previous_earnings_date=date.fromisoformat(row["previous_earnings_date"]),
                )


def _timing_from_text(value: str | None) -> EarningsTiming:
    text = (value or "").strip().lower()
    if text in {"bmo", "before market open", "before open", "pre-market", "premarket"}:
        return EarningsTiming.BMO
    if text in {"amc", "after market close", "after close", "post-market", "postmarket"}:
        return EarningsTiming.AMC
    if text in {"during", "during market", "market hours"}:
        return EarningsTiming.DURING
    return EarningsTiming.UNKNOWN


class FmpEarningsProvider:
    """Financial Modeling Prep earnings-calendar adapter.

    It queries a wider historical window so each returned upcoming event can be
    paired with the latest earlier earnings date for the same ticker.
    """

    def __init__(
        self,
        api_key: str,
        fetcher: Callable[[str], str] | None = None,
        base_url: str = "https://financialmodelingprep.com/stable/earnings-calendar",
    ):
        self.api_key = api_key
        self.fetcher = fetcher or self._default_fetcher
        self.base_url = base_url

    def _default_fetcher(self, url: str) -> str:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8")

    def _fetch(self, start: date, end: date) -> list[dict]:
        query = urllib.parse.urlencode(
            {
                "from": start.isoformat(),
                "to": end.isoformat(),
                "apikey": self.api_key,
            }
        )
        print(f"{self.base_url}?{query}")
        return json.loads(self.fetcher(f"{self.base_url}?{query}"))

    def events(self, start: date, end: date) -> Iterable[EarningsEvent]:
        # lookback_start = start - timedelta(days=460)
        # rows = self._fetch(lookback_start, end)
        rows = self._fetch(start, end)
        dated: list[tuple[str, date, EarningsTiming]] = []
        for row in rows:
            symbol = (row.get("symbol") or row.get("ticker") or "").strip().upper()
            raw_date = row.get("date") or row.get("epsDate") or row.get("earnings_date")
            if not symbol or not raw_date:
                continue
            earnings_date = date.fromisoformat(str(raw_date)[:10])
            timing = _timing_from_text(row.get("time") or row.get("timing"))
            dated.append((symbol, earnings_date, timing))
        dated.sort(key=lambda item: (item[0], item[1]))
        previous_by_ticker: dict[str, date] = {}
        for symbol, earnings_date, timing in dated:
            previous = previous_by_ticker.get(symbol)
            previous_by_ticker[symbol] = earnings_date
            if not start <= earnings_date <= end or previous is None:
                continue
            yield EarningsEvent(
                ticker=symbol,
                earnings_date=earnings_date,
                timing=timing,
                previous_earnings_date=previous,
            )
