from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from ..calendar_utils import next_weekday
from ..config import DataConfig
from ..models import EarningsEvent, EarningsTiming, InsiderTransaction


class CsvMarketDataProvider:
    def __init__(self, config: DataConfig):
        self.config = config
        self._events = _read_earnings(config.earnings_csv)
        self._priors = _read_priors(config.prior_earnings_csv)
        self._transactions = _read_transactions(config.insider_csv)
        self._prices = _read_prices(config.price_csv)

    def get_earnings_events(self, run_date: date) -> list[EarningsEvent]:
        target_dates = {run_date, next_weekday(run_date)}
        return [event for event in self._events if event.report_date in target_dates]

    def get_prior_earnings_date(self, ticker: str, next_earnings_date: date) -> date | None:
        return self._priors.get(ticker.upper())

    def get_insider_transactions(
        self,
        ticker: str,
        since: date,
        until: date,
    ) -> list[InsiderTransaction]:
        symbol = ticker.upper()
        return [
            tx
            for tx in self._transactions
            if tx.ticker.upper() == symbol and since < tx.transaction_date <= until
        ]

    def get_last_price(self, ticker: str) -> float:
        return self._prices.get(ticker.upper(), 0.0)


def _read_earnings(path: Path) -> list[EarningsEvent]:
    rows = _read_rows(path)
    return [
        EarningsEvent(
            ticker=row["ticker"].upper(),
            report_date=date.fromisoformat(row["report_date"]),
            timing=EarningsTiming(row["timing"].upper()),
            exchange=row.get("exchange", "").upper(),
        )
        for row in rows
    ]


def _read_priors(path: Path) -> dict[str, date]:
    return {
        row["ticker"].upper(): date.fromisoformat(row["prior_earnings_date"])
        for row in _read_rows(path)
    }


def _read_transactions(path: Path) -> list[InsiderTransaction]:
    return [
        InsiderTransaction(
            ticker=row["ticker"].upper(),
            buyer_id=row.get("buyer_id", "") or row.get("buyer_name", ""),
            buyer_name=row.get("buyer_name", ""),
            role=row.get("role", ""),
            source=row.get("source", "corporate"),
            transaction_date=date.fromisoformat(row["transaction_date"]),
            shares=float(row["shares"]),
            price=float(row["price"]),
            planned_10b5_1=_parse_bool(row.get("planned_10b5_1", "false")),
            disclosed_date=_parse_optional_date(row.get("disclosed_date", "")),
        )
        for row in _read_rows(path)
    ]


def _read_prices(path: Path) -> dict[str, float]:
    return {row["ticker"].upper(): float(row["price"]) for row in _read_rows(path)}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _parse_optional_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    return date.fromisoformat(value)
