from __future__ import annotations

from datetime import date
from typing import Protocol

from ..models import EarningsEvent, InsiderTransaction


class MarketDataProvider(Protocol):
    def get_earnings_events(self, run_date: date) -> list[EarningsEvent]:
        ...

    def get_prior_earnings_date(self, ticker: str, next_earnings_date: date) -> date | None:
        ...

    def get_insider_transactions(
        self,
        ticker: str,
        since: date,
        until: date,
    ) -> list[InsiderTransaction]:
        ...

    def get_last_price(self, ticker: str) -> float:
        ...
